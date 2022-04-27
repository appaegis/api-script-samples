### Prerequisite

#### Create API key if you haven't done so:
- Login to your Appaegis access cloud account
- Select "Setting --> API Keys" from the menu on the left side of the window
- Click the "+ API Key" button (Please note the API secret string is only displayed once)

#### Review our API document here:
- [https://api.appaegis.net/api/v1/api-docs/](https://api.appaegis.net/api/v1/api-docs/)


### Quickstart

#### For `ubuntu` 20.04 LTS and `ptyhon` 3.8.5 and `virtualenv` util
```
sudo apt install virtualenv
virtualenv .venv -p python3
source .venv/bin/activate
```
- Make sure you've give execution permission(`chmod +x`) to those script files.

#### Create python local environment at project root path
```
pip install -r requirements.txt
```

#### Use environment variable as input for script, for example:

- ex-01: Variable injecting with export

```
export API_HOST=https://api.appaegis.net  # optionally customize the API root
export API_KEY=abcd................................
export API_SECRET=abcd.............................

export USER_EMAIL=user@companydomain.com
export USER_SSH_IP=127.0.0.2:3333

./create-user.py
./purge-user.py --dryrun=True
```

- ex-02: Inline variable injection works as well

```
USER_EMAIL=bbb API_KEY=ddd API_SECRET=eee ./purge-user.py --dryrun True
```

:information_source: After the `create-user.py` script is finished, go ask your user to check his/her email box to find the invitation.

:warning: Please always dryrun before actrually deleting resource, because the deletion cannot be undone.  
Data searching will start from userEntry, so circular references without user as foreignKey will not be removed. ex:`Team <-> Role` only without `user` reference.  
If process is terminated before completion, the data relationship might be broken.

- ex-03: List all networks in json format

```
export API_KEY=abcd................................
export API_SECRET=abcd.............................

./list-se.py
```

- ex-04: List all service edge of one network in json format

```
export API_KEY=abcd................................
export API_SECRET=abcd.............................

./list-se.py --nwname "my network"
```
