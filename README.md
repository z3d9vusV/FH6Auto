# FH6Auto

A visual scripting tool for FH6 based on **Python + image recognition + input automation**.  
Supports **looping through maps / bulk vehicle purchases / super raffles / vehicle removal / multi-module chaining / infinite loop idling**.

> For Python automation technical exchange and learning purposes only; please do not use for commercial purposes or to disrupt game balance.  
> Users shall bear full responsibility for any consequences arising from the use of this tool (including but not limited to account bans, system errors, financial losses, etc.).

---

## Project Overview

FH6Auto is a desktop automation tool designed around automatic game interface recognition and workflow control.  
The project utilises **image recognition** as the core of its workflow guidance, minimising the risk of uncontrolled behaviour associated with pure keystroke scripts.

The tool achieves automated execution through the following methods:

- Capturing screenshots to recognise the current game state
- Dynamically determining whether the target page has been entered
- Triggering keyboard / mouse operations
- Automatically attempting to restore the runtime environment in the event of an error

Compared to traditional pure keystroke scripts, this project offers superior stability, adaptability and controllability.

---

## Feature Modules

### 1. Loop Map Runs
- Automatically access the menu
- Automatically switch between Creative Centre and EventLab
- Automatically enter blueprint sharing codes
- Automatically match target vehicles
- Automatically loop through race starts
- Supports repeating the process a set number of times

### 2. Bulk Vehicle Purchases
- Automatically access the vehicle collection
- Automatically locate the target brand
- Automatically select the specified vehicle
- Automatically repeat the purchase
- Supports batch execution for a set number of times

### 3. Super Prize Draw
- Automatically enter the vehicle purchase process
- Automatically locate the target vehicle
- Automatically access the upgrade / proficiency interface
- Automatically allocate skill points according to the skill matrix
- Supports automatic termination of the module once skill points are exhausted


### 4. Endless Loop
Supports chaining modules to form a complete workflow:

**Map Run → Car Purchase → Lottery → Reset Count → Next Round**

Configurable options:
- Whether to proceed to the next module
- Whether to restart the loop after three modules are completed
- Total number of loops
- Near-infinite loop execution


## How to Use

### 1. Preparations Before Starting

#### Vehicle Preparation
Please first purchase a **Subaru Impreza 22B-STi Version** for map running and complete the following preparations:

- Tune to **S2 900**
- Add this vehicle to your collection
- Ensure there are no liveries applied

#### Recommended checks before use
- **Disable any filters, HDR or other features that affect colour**
- Ensure the game has launched correctly
- Ensure the keyboard layout is **English keyboard**
- In-game settings: **Auto-steer**, **Automatic transmission**, difficulty set to **Unstoppable**
- Keep the game interface as stable as possible
- Do not switch to other windows arbitrarily, as this may affect image recognition results

---

### 2. Configuration Parameters

The following can be set on the main interface of the programme:

- Number of runs
- Number of car purchases
- Number of draws
- Blueprint share code
- Total number of cycles
- Whether to chain to the next module
- Enable three-module loop
- Enable auto-restart mechanism
- Auto-restart command

---

### 3. Setting Skill Paths

In the ‘Super Draw’ module area:

- Tap the directional buttons to add skill paths
- Tap ‘Clear Matrix’ to reset paths
- Blue squares indicate the current skill movement path

---

### 4. Launching Individual Modules

Any module can be launched independently:

- Map Loop
- Bulk Car Purchase
- Super Draw

The programme will begin execution from the corresponding module.

---

### 5. Launching a Sequential Process

If the “Continue” option (indicated by the arrow) is ticked, the modules will automatically link together, for example:

- Continue with car purchase after map loop is complete
- Continue with the draw after car purchase is complete

If you also tick `LOOP -> Reset Loop`, the system will automatically proceed to the next round once all three modules are complete.

---

### 6. Stopping the script

You can stop the script in the following ways:

- Click the Stop button on the interface
- Press

Translated with DeepL.com (free version)
