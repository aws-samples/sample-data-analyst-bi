# © 2023 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.

# This AWS Content is provided subject to the terms of the AWS Customer Agreement
# available at http://aws.amazon.com/agreement or other written agreement between
# Customer and either Amazon Web Services, Inc. or Amazon Web Services EMEA SARL or both.

# License terms can be found at: https://aws.amazon.com/legal/aws-ip-license-terms/

import argparse
import os
import sys

import torch
from datasets import load_from_disk
from peft import (AutoPeftModelForCausalLM, LoraConfig, get_peft_model, get_peft_model_state_dict,
                  TaskType, prepare_model_for_kbit_training, prepare_model_for_int8_training)
from transformers import (AutoTokenizer, AutoModelForCausalLM, set_seed, TrainingArguments, Trainer,
                          BitsAndBytesConfig, DataCollatorForLanguageModeling)


def print_trainable_parameters(model):
    """
    Prints the number of trainable parameters in the model.
    """
    trainable_params = 0
    all_param = 0
    for _, param in model.named_parameters():
        all_param += param.numel()
        if param.requires_grad:
            trainable_params += param.numel()
    print(
        f"trainable params: {trainable_params} || all params: {all_param} || trainable%: {100 * trainable_params / all_param}"
    )

def parse_arge():
    """Parse the arguments."""
    parser = argparse.ArgumentParser()
    # add model id and dataset path argument
    parser.add_argument(
        "--model_id",
        type=str,
        default="codellama/CodeLlama-7b-Instruct-hf",
        help="Model id to use for training.",
    )
    parser.add_argument("--train_ds_path", type=str, default="train_set", help="Path to dataset.")
    parser.add_argument("--val_ds_path", type=str, default="val_set", help="Path to dataset.")
    # add training hyperparameters for epochs, batch size, learning rate, and seed
    parser.add_argument("--max_steps", type=int, default=40, help="Max number of steps to train for.")
    parser.add_argument("--train_kbit", type=bool, default=True, help="Whether to load and tune 4bit model")
    parser.add_argument("--batch_size", type=int, default=16, help="Batch size to use for training.")
    parser.add_argument(
        "--per_device_train_batch_size",
        type=int,
        default=8,
        help="Batch size to use for training on per device.",
    )
    parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate to use for training.")
    parser.add_argument("--seed", type=int, default=42, help="Seed to use for training.")
    parser.add_argument(
        "--merge_weights",
        type=bool,
        default=True,
        help="Whether to merge LoRA weights with base model.",
    )
    args, _ = parser.parse_known_args()

    return args


def training_function(args):
    # set seed
    set_seed(args.seed)

    train_ds = load_from_disk(args.train_ds_path)
    val_ds = load_from_disk(args.val_ds_path)
    # load model from the hub with a bnb config

    if args.train_kbit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id,
            quantization_config=bnb_config,
            device_map="auto",
        )
        model.gradient_checkpointing_enable()
        model = prepare_model_for_kbit_training(model)
        config = LoraConfig(
            r=16,
            lora_alpha=16,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "w1",
                "w2",
                "w3",
                "lm_head",
            ],
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )
        optimizer = "paged_adamw_8bit"

    else:
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id,
            device_map={'': torch.cuda.current_device()}
        )
        model.gradient_checkpointing_enable()  # put model back into training mode
        optimizer = "adamw_torch"
        config = LoraConfig(task_type=TaskType.CAUSAL_LM,
                            inference_mode=False, r=8,
                            lora_alpha=16, lora_dropout=0.1)
    
    model = get_peft_model(model, config)
    print_trainable_parameters(model)

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    tokenizer.add_eos_token = True
    tokenizer.pad_token_id = 0
    tokenizer.padding_side = "left"

    if torch.cuda.device_count() > 1:
        # keeps Trainer from trying its own DataParallelism when more than 1 gpu is available
        model.is_parallelizable = True
        model.model_parallel = True

    gradient_accumulation_steps = args.batch_size // args.per_device_train_batch_size
    output_dir = "/opt/ml/output/data/"

    training_args = TrainingArguments(
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        warmup_steps=int(max(int(args.max_steps/4), 1)),
        max_steps=args.max_steps,
        learning_rate=args.lr,
        fp16=True,
        logging_steps=2,
        optim=optimizer,
        evaluation_strategy="steps",  # if val_set_size > 0 else "no",
        save_strategy="steps",
        eval_steps=2,
        save_steps=2,
        output_dir=output_dir,
        load_best_model_at_end=False,
        group_by_length=True,  # group sequences of roughly the same length together to speed up training
        # logging strategies
        logging_dir=f"{output_dir}/logs",
        logging_strategy="steps",
    )

    trainer = Trainer(
        model=model,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        args=training_args,
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    model.config.use_cache = False

    old_state_dict = model.state_dict
    model.state_dict = (lambda self, *_, **__: get_peft_model_state_dict(self, old_state_dict())).__get__(
        model, type(model))
    if torch.__version__ >= "2" and sys.platform != "win32":
        print("compiling the model")
        model = torch.compile(model)
    trainer.train()

    sagemaker_save_dir = "/opt/ml/model/"
    if args.merge_weights:
        # merge adapter weights with base model and save
        # save int 4 model
        trainer.model.save_pretrained(output_dir, safe_serialization=False)
        # clear memory
        del model
        del trainer
        torch.cuda.empty_cache()

        # load PEFT model in fp16
        model = AutoPeftModelForCausalLM.from_pretrained(
            output_dir,
            low_cpu_mem_usage=True,
            torch_dtype=torch.float16,
        )
        # Merge LoRA and base model and save
        model = model.merge_and_unload()
        model.save_pretrained(sagemaker_save_dir, safe_serialization=True, max_shard_size="2GB")
    else:
        trainer.model.save_pretrained(sagemaker_save_dir, safe_serialization=True)

    # save tokenizer for easy inference
    tokenizer.save_pretrained(sagemaker_save_dir)


def main():
    args = parse_arge()
    training_function(args)


if __name__ == "__main__":
    main()
