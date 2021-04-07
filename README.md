#### Prerequisite

- For `ubuntu` 20.04 LTS and `ptyhon` 3.8.5 and `virtualenv` util
```
sudo apt install virtualenv
virtualenv .venv -p python3
source .venv/bin/activate
```
- Make sure you've give execution permission(`chmod +x`) to those script files.
- Get the `API_KEY` and `API_SECRET` and `API_HOST` from web-portal(you can take a look at the test scripts)

#### Quickstart

###### Create python local environment at project root path

```
pip install -r requirements.txt
```

###### Use environment variable as input for script, there are two script named: `create-user.py` and `purge-user.py`, example below:
- ex-01: Variable injecting with export 

```
export API_HOST=https://api.appaegis.net  # using root domain without base path
export API_KEY=abcd................................
export API_SECRET=abcd.............................

export USER_EMAIL=user@companydomain.com
export USER_SSH_IP=127.0.0.2:3333

./create-user.py
./purge-user.py --dryrun=True
```

- ex-02: Inline variable injection works as well

```
API_HOST=aaa USER_EMAIL=bbb API_KEY=ddd API_SECRET=eee ./purge-user.py --dryrun True
```

- After the `create-user.py` script is finished, go ask your user to check his/her email box to find the invitation.

#### Caution

- Please always dryrun before actrually deleting resource, because the delete will not be able to undo.
- Data searching will start from userEntry, so circular references without user as foreignKey will not be removed. ex: `Team <-> Role` only without `user` reference.
- If process is terminated somehow, the data relationship might be broken.

