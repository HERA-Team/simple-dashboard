FROM conda/miniconda2
WORKDIR /src
COPY . /src
#RUN pip install --trusted-host pypi.python.org -r requirements.txt
RUN conda install redis-py numpy astropy
