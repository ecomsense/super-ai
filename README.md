### GOALS ###
we want to some resusable modules and function so we can concentrate on the strategies.
if everything works correctly, we should be able to switch to another broker without doing any/much change

## files and their roles ##
**constants.py**

```
project-name
  -- factory/
     -- *.yml
     -- *.csv
  -- src/
     -- constants.py
```
- want yml files and csv files to be configured by user in a factory folder.
- at the time of installation we will copy these files to the data directory.
- these files will not be overwritten if it is already present.
- also evaluates them to check if user inputs are of valid types
- finally it exposes some global objects that can be imported into other files.

**api.py**

the credentials to be named as `name_project.yml` need to be placed outside the github repository and `CNFG` object need to created in constants.py from it.
```
# ../../name_project.yml

brokername:
   userid: <>
   apikey: <>
```
api should be able to authenticate itself again in case of api errors and exceptions.
we work with class variable so, we should be able to access it in one liners from anywhere we want.

**symbols.py**

this is the place where most of the heavy lifting is needed. also currently this is the biggest hurdle in making our projects broker agnostic.
- symbols are subset of master data provided by broker
- should download necessary symbol masters based on the `symbols.yml` set by user/developer
- mainly downloads master and stores token info.
- also builds option chain map
- should cover all variations of strategies
```
#../data/symbols.yml

exchanges:
 - NFO
NSE:
  "NIFTY BANK":
      token: 26001
```

**wserver.py**

should speak with api.py directly to get quotes.
if we send exchange:tradingsymbol as a list, wserver should be able to provide the ltp.
if subscribtion needs to be done, it should be done automatically. 
if no websocket then ltp should be returned as normal http request.

**books.py**

should speak with api.py directly to download order book, position book.
if paper trade is enabled, then it needs to manifest its own books.
variations of strategies should be possible. in that case, one strategy may paper trade while other will be on live mode.

**main.py**

`..\data\main.yml` will have tell when all the strategies should be started.
```
start_time: 9:!5
stop_time: 15:30
strategies:
  - strategy1
  - strategy5
```
it should be responsible to start all strategies

**universe.py**

looks for yml and/or csv file, so that it can arrive at a subset of symbol and tokens produced by the symbol file. the details of the symbols to be subscribed is deduced from the below strategy yml files.

**strategies/**

```
# ..\data\strategy1.yml
log_level: DEBUG
show_log: 1
live_trading: 1
base: BANKNIFTY
BANKNIFTY:
    strike: -1
    expiry: 24JUN
```
strategies juggles around massive dictionary that contain every possible information. they could hold parameters, function names and class instances.

