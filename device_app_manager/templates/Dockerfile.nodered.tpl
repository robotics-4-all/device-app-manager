FROM nodered/node-red

ENV NODE_RED_ENABLE_SAFE_MODE false
ENV NODE_RED_ENABLE_PROJECTS false

COPY ./app/package.json /data/package.json

WORKDIR /data

RUN npm install --unsafe-perm --no-update-notifier --no-fund --only=production

WORKDIR /usr/src/node-red

# COPY ./app/settings.js /data/settings.js
# COPY ./app/flows_cred.json /data/flows_cred.json
COPY ./app/flows.json /data/flows.json

ENTRYPOINT ["npm", "start", "--cache", "/data/.npm", "--", "--userDir", "/data"]
