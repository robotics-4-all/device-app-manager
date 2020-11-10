FROM nodered/node-red

ENV NODE_RED_ENABLE_SAFE_MODE false
ENV NODE_RED_ENABLE_PROJECTS false

# COPY ./app/settings.js /data/settings.js
# COPY ./app/flows_cred.json /data/flows_cred.json
COPY ./app/flows.json /data/flows.json

ENTRYPOINT ["npm", "start", "--cache", "/data/.npm", "--", "--userDir", "/data"]
