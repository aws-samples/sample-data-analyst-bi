#Variables related to Indexing for Few-Shot Inference
fewshot_run_indexing=true
fewshot_indexing_delete_all_conflicts="Y"

#Variables for Finetuning and Deployment
hf_run_finetuning=true
hf_deploy_model=true
finetune_conf="../conf/finetuning_config.yaml"
deployment_conf="../conf/deployment_config.yaml"
use_djl_deployment="Y"

case "$1" in
    "zero-shot") echo 'You opted for zero-shot inference setup.' ;;
    "few-shot") echo 'You opted for few-shot inference setup.' ;;
    "hf-deploy") echo 'You opted for inference using pretrained huggingface model.' ;;
    "hf-finetune") echo 'You opted for inference using finetuned huggingface model.' ;;
    "") echo 'No input argument provided... using default zero-shot inference setup.' ;;
    *) echo 'Warning: Input argument must be one of: zero-shot / few-shot / hf-deploy / hf-finetune'
        exit 1 ;;
esac

#Configure OpenSearch index for few-shot inference (optional)
if [ $1 == "few-shot" ]
then
    if [ "$fewshot_run_indexing" = true ]; then
        if [[ "$fewshot_indexing_delete_all_conflicts" =~ ^[Yy]$ ]]; then
            read -p "As per configuration, conflicting OpenSearch index (if existing) would be deleted and a new index will be created afresh. Do you want to proceed [Y / N] ? " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then     
                echo "Aborting operation."
                exit 1;  
            fi
        fi
        echo "Running Indexing for few-shot inference . . ."
        cd scripts
        python support/aoss_indexer.py --purpose setup --delete_all_conflicts "$fewshot_indexing_delete_all_conflicts"
        python support/aoss_indexer.py --purpose indexing
        cd ../
    fi
fi

#Deploy HF model for inference (optional)
if [ $1 == "hf-deploy" ]
then
    if [ "$hf_deploy_model" = true ]; then
        echo "Deploying finetuned model . . ."
        cd scripts
        python deployer.py --deployment_config_file "$deployment_conf" --djl_deployment "$use_djl_deployment"
        cd ../
    fi
fi

#Finetune and deploy HF model for inference (optional)
if [ $1 == "hf-finetune" ]
then
    if [ "$hf_run_finetuning" = true ]; then
        echo "Running Finetuning process . . ."
        cd scripts
        python trainer.py --ft_config_path "$finetune_conf"
        cd ../
    fi
    if [ "$hf_deploy_model" = true ]; then
        echo "Deploying finetuned model . . ."
        cd scripts
        python deployer.py --deployment_config_file "$deployment_conf" --djl_deployment "$use_djl_deployment"
        cd ../
    fi
fi

#Start streamlit demo app
echo "Starting streamlit server . . ."
cd apps
streamlit run demo_app.py --server.fileWatcherType none
