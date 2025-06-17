From public.ecr.aws/lambda/python:3.8

COPY requirements.txt ./

RUN pip3 install --no-cache-dir -r requirements.txt

COPY . ${LAMBDA_TASK_ROOT}

CMD ["lambda_function.lambda_handler"]

