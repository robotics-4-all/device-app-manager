FROM tektrain/nodered

# Copy package.json to the WORKDIR so npm builds all
# of your added nodes modules for Node-RED
COPY package.json .
RUN npm install --unsafe-perm --no-update-notifier --no-fund --only=production

# You should add extra nodes via your package.json file but you can also add them here:
WORKDIR /usr/src/node-red

# Copy _your_ Node-RED project files into place
# NOTE: This will only work if you DO NOT later mount /data as an external volume.
#       If you need to use an external volume for persistence then
#       copy your settings and flows files to that volume instead.
# COPY settings.js /data/settings.js
# COPY flows_cred.json /data/flows_cred.json
COPY flows.json /data/flows.json
