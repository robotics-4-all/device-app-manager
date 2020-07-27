FROM r4a/app-commlib

COPY {{ app_src_dir }} {{ app_dest_dir }}

WORKDIR {{ app_dest_dir }}

RUN pip install -r requirements.txt
CMD ["python", "-u",  "app.py"]
