FROM {{ image }}

COPY {{ app_src_dir }} {{ app_dest_dir }}

WORKDIR {{ app_dest_dir }}

# RUN pip3 install -r requirements.txt

CMD ["python3", "-u",  "app.py"]
