FROM public.ecr.aws/lambda/python:3.9

ENV MPLCONFIGDIR=/tmp

WORKDIR /var/task

RUN pip install \
    matplotlib \
    pillow \
    pandas \
    pyarrow \
    s3fs==2023.6.0 \
    --no-cache-dir

COPY lambda_function.py ./

CMD ["lambda_function.lambda_handler"]

