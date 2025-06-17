"""
Module for running the RAG Web App

Copyright 2023 Amazon.com and its affiliates; all rights reserved.
This file is Amazon Web Services Content and may not be duplicated
or distributed without permission.
"""

import sys

sys.path.insert(0, '../')

from scripts.sql.generator import SQLGeneratorBedrock, SQLGeneratorHF
from scripts.sql.executor import get_database_helper
from scripts.sql.interpreter import Interpreter
import logging
import json
import yaml

import boto3
import pandas as pd
import streamlit as st
from botocore.client import Config

logging.basicConfig(level=logging.INFO)


def set_static_session_state():
    """
    Set static session variable values for the streamlit app
    """
    with open(f"../conf/session_values.json", encoding="utf-8") as fp:
        mappings = json.load(fp)
        for key, value in mappings.items():
            if key not in st.session_state:
                st.session_state[key] = value


def set_clients():
    """
    Function to set the required Bedrock clients
    """

    bedrock_config = Config(
        connect_timeout=st.session_state["connect_timeout"],
        read_timeout=st.session_state["read_timeout"],
        retries={"max_attempts": st.session_state["max_attempts"]},
    )
    session = boto3.Session(region_name=st.session_state["aws_region"])
    st.session_state["bedrock_client"] = session.client("bedrock-runtime")


def model_chooser_on_change():
    """
    Function to present the model changes
    """
    with st.sidebar:
        st.success(f"Select {st.session_state.model_selector}", icon="✅")


def db_chooser_on_change():
    """
    Function to present the DB changes
    """
    with st.sidebar:
        st.success(f"Select {st.session_state.db_selector}", icon="✅")


def generate_page():
    """
    Function to generate the landing page
    """
    with st.sidebar:
        model_selector = st.selectbox(
            label="Model Selector",
            options=st.session_state["model_ids"],
            key="model_selector",
            index=0,
            on_change=model_chooser_on_change,
            label_visibility="visible",
            help="Make sure that the selected model was configured and made available during the setup and run process."
        )

        with st.expander("Settings"):

            temp = st.slider(
                "temperature",
                0.0,
                1.0,
                st.session_state["default_model_parameters"]["temperature"],
            )
            top_p = st.slider(
                "top_p",
                0.0,
                1.0,
                st.session_state["default_model_parameters"]["top_p"],
            )
            top_k = st.slider(
                "top_k",
                0,
                250,
                st.session_state["default_model_parameters"]["top_k"],
            )
            max_tokens_to_sample = st.slider(
                "max_tokens_to_sample",
                0,
                5000,
                st.session_state["default_model_parameters"]["max_tokens_to_sample"],
            )

        db_selector = st.selectbox(
            label="Database Selector",
            options=st.session_state["database_options"],
            key="db_selector",
            index=0,
            on_change=db_chooser_on_change,
            label_visibility="visible",
            help="Make sure that the selected database is available and accessible."
        )

        db_cred_help_txt = "Not required for SQLite DB"
        db_user = st.text_input("DB User", "", help = db_cred_help_txt)
        db_passwd = st.text_input("DB Password", type="password",  help = db_cred_help_txt)

        clear_button = st.button(label="Clear Chat", key="clear_chat")

        with st.expander("Sample Questions"):
            st.code("How many total teachers are there?")
            st.code("What is the average salary of instructors?")
            st.code("What are the distinct buildings with capacities of greater than 50?")
            st.code("Find the title of courses that have two prerequisites?")
            st.code(
                "What is the title of the course that was offered at building Chandler during the fall semester in the year of 2010?"
            )
    st.title("💬 QueryBot: interacts with database")
    st.write("🚀 A streamlit chatbot powered by AWS BedRock and SageMaker")

    # Set model args
    model_args = {
        "temperature": temp,
        "top_p": top_p,
        "top_k": top_k,
        "max_tokens_to_sample": max_tokens_to_sample,
    }

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    with open(st.session_state["db_conf"], 'r') as file:
        db_conf = yaml.safe_load(file)

    if question := st.chat_input():
        st.session_state.messages.append({"role": "user", "content": question})
        st.chat_message("user").write(question)

        database_type = db_conf[db_selector]['database_type']
        db_conn_conf = db_conf[db_selector]['db_conn_conf']
        db_schema_file = db_conf[db_selector]['db_schema_file']
        if database_type == "PostgreSQL":
            db_conf[db_selector]['db_conn_conf']['user'] = db_user
            db_conf[db_selector]['db_conn_conf']['password'] = db_passwd

        model_id = model_selector
        generator_function = None
        if model_id.strip() in ["zs-pretrained-sqlcoder-v1", "zs-finetuned-codellama-v1"]:
            #endpoint_name = st.session_state["zs-finetuned-codellama-v1"]
            with open(st.session_state[model_id.strip()], 'r') as f:
                endpoint_name = f.read().strip()
            approach = 'zero_shot'
            model_args = {"temperature": temp, "runtime_top_p": top_p, "runtime_top_k": top_k}
            sql_generator = SQLGeneratorHF(endpoint_name, approach, database_type, db_conn_conf, db_schema_file,
                                           model_args)
            generator_function = sql_generator.generate_zeroshot
        elif model_id.strip().startswith("icl-"):
            model_id = model_id.replace("icl-", "")
            approach = 'few_shot'
            with open(st.session_state["aoss_host"], 'r') as f:
                data = yaml.safe_load(f)
                aoss_host = data['aoss_host']
                aoss_index_name = data['aoss_index_name']
            fewshot_count = st.session_state["fewshot_count"]
            sql_generator = SQLGeneratorBedrock(model_id, approach, database_type, db_conn_conf, db_schema_file,
                                                aoss_host, aoss_index_name, model_args, fewshot_count)
            generator_function = sql_generator.generate_fewshot
        else:
            model_id = model_id.replace("zs-", "")
            approach = 'zero_shot'
            sql_generator = SQLGeneratorBedrock(model_id, approach, database_type, db_conn_conf, db_schema_file,
                                                model_args)
            generator_function = sql_generator.generate_zeroshot

        sql = generator_function(question)

        try:
            db_helper = get_database_helper(database_type,
                                            db_conn_conf,
                                            None,
                                            model_id,
                                            model_args,
                                            st.session_state["max_attempts"],
                                            schema_file=db_schema_file)
            res, sql = db_helper.run_sql(question, sql)
        except Exception as e:
            """Format the error message"""
            logging.info(e)
            res = f"{e}"
        st.chat_message("assistant").write(sql)
        st.chat_message("assistant").write(res)

        summary = ""
        if isinstance(res, pd.DataFrame) and model_id in Interpreter.SUPPORTED_MODELS:
            try:
                interpreter = Interpreter(model_id, model_args)
                summary = interpreter.explain(question, res)
            except Exception as e:
                logging.info(e)
                summary = f"Error: {e}"
            with st.expander("See explanation"):
                st.chat_message("assistant").write(summary)

        st.session_state.messages.append({"role": "user", "content": question})
        st.session_state.messages.append({"role": "assistant", "content": sql, "result table": res, "summary": summary})

    if clear_button:
        st.session_state.messages = []


def run():
    """
    Function to orchestrate the application
    """
    set_static_session_state()
    set_clients()
    generate_page()


if __name__ == "__main__":
    run()
