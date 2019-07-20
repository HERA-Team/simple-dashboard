FROM conda/miniconda2
WORKDIR /src
COPY . /src
#RUN pip install --trusted-host pypi.python.org -r requirements.txt
RUN apt update && apt install -y procps
RUN conda install redis-py numpy astropy
