# Benchmark Report: BERT vs DSPy (Few-Shot)

**Sample Size**: 302
**Test Dataset**: benchmark_silver_2.jsonl
**Few-Shot Examples**: 10

## 🏆 Overall Accuracy
| Model | Accuracy | Correct |
| :--- | :--- | :--- |
| **BERT (Baseline)** | **42.7%** | 129/302 |
| **DSPy (DeepSeek)** | **90.7%** | 274/302 |

## 🔍 Detailed Errors
Cases where models disagreed or failed.

| Context | Pair | Ground Truth | BERT | DSPy | DSPy Reasoning |
| :--- | :--- | :--- | :--- | :--- | :--- |
| If the battery level is under 20%, switc... | If not -> maintain high performance | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the database is locked, wait for rele... | database is locked -> wait for release | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The streaming service buffers the video ... | buffers the video -> downloading the subtitles | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The pharmacist checks for drug interacti... | checks for drug interactions -> processes the insurance | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The security guard patrols the perimeter... | patrols the perimeter -> monitoring the CCTV feed | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the user is a premium member, remove ... | user is a premium member -> remove ads | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the voltage is unstable, switch to th... | voltage is unstable -> switch to the backup generator | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the order value is above $1000, apply... | Otherwise -> charge $50 for shipping | **FALSE_BRANCH** | ❌ CONDITION_DEF | ✅ FALSE_BRANCH | No reasoning... |
| If the patient condition is critical, ad... | Else -> admit to the general ward | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the payment gateway times out, retry ... | payment gateway times out -> retry the transaction | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| Should the applicant fail the background... | Should -> applicant fail the background check | **CONDITION_DEF** | ❌ SEQUENCE | ✅ CONDITION_DEF | No reasoning... |
| If the smoke detector is triggered, soun... | smoke detector is triggered -> sound the alarm | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The doctor examines the X-ray while the ... | examines the X-ray -> records the patient history | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The nurse draws blood while the doctor p... | draws blood -> prepares the vaccination | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the patient reports pain, administer ... | patient reports pain -> administer painkillers | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| Should the applicant fail the background... | applicant fail the background check -> send a rejection letter | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the loan-to-value ratio is high, requ... | loan-to-value ratio is high -> request mortgage insurance | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The system validates the invoice format ... | validates the invoice format -> checking for duplicate entries | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the patient is allergic to penicillin... | patient is allergic to penicillin -> prescribe erythromycin | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the employee is full-time, enroll the... | employee is full-time -> enroll them in the 401k plan | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the employee is full-time, enroll the... | Otherwise -> skip enrollment | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the voltage drops, trigger the alarm.... | voltage drops -> trigger the alarm | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the inventory is sufficient, release ... | If not -> trigger a procurement request | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the patient reports pain, administer ... | Otherwise -> monitor vitals | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the user creates a password, hash it ... | Else -> do not store it | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the input is a number, perform the ca... | input is a number -> perform the calculation | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the logic gate receives a high signal... | Else -> output false | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| The agent verifies the customer ID while... | verifies the customer ID -> retrieves the account details | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the user is underage, block access to... | Otherwise -> allow entry | **FALSE_BRANCH** | ❌ CONDITION_DEF | ✅ FALSE_BRANCH | No reasoning... |
| If the user is an admin, show the settin... | user is an admin -> show the settings panel | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the disk space is full, delete tempor... | disk space is full -> delete temporary files | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The qa engineer writes the test plan whi... | writes the test plan -> defines the acceptance criteria | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the visa is approved, stamp the passp... | visa is approved -> stamp the passport | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The graphic designer creates the assets ... | creates the assets -> writes the slogan | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the user selects the dark theme, appl... | user selects the dark theme -> apply the dark CSS | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The manufacturing line assembles the cha... | assembles the chassis -> mixes the colors | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the candidate passes the coding test,... | candidate passes the coding test -> schedule an interview | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the warranty is valid, repair the dev... | If expired -> charge for parts and labor | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the payment gateway times out, retry ... | Otherwise -> cancel the order | **FALSE_BRANCH** | ❌ CONDITION_DEF | ✅ FALSE_BRANCH | No reasoning... |
| If the password complexity is low, promp... | password complexity is low -> prompt for a stronger password | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the transaction is suspicious, flag i... | transaction is suspicious -> flag it for review | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The designer sketches the layout while t... | sketches the layout -> sets up the repository | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The qa team runs the regression suite wh... | runs the regression suite -> fixes the reported bugs | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the email is marked as spam, move it ... | email is marked as spam -> move it to the junk folder | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the traffic is heavy, take the detour... | If the road is clear -> stay on the highway | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the inventory is sufficient, release ... | inventory is sufficient -> release the order | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the flight is delayed, send an alert ... | flight is delayed -> send an alert | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the blood sugar is low, give the pati... | blood sugar is low -> give the patient orange juice | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the document is signed, file it in th... | document is signed -> file it in the registry | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the user is underage, block access to... | user is underage -> block access | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The app requests location permissions wh... | requests location permissions -> map data loads | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the product is out of stock, notify t... | Otherwise -> create a shipping label | **FALSE_BRANCH** | ❌ CONDITION_DEF | ✅ FALSE_BRANCH | No reasoning... |
| If the item is fragile, wrap it in bubbl... | item is fragile -> wrap it in bubble wrap | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the subscription renews automatically... | subscription renews automatically -> charge the stored card | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the battery level is under 20%, switc... | battery level is under 20% -> switch to power saving mode | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the water level is low, open the inta... | water level is low -> open the intake valve | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The IT team provisions the user account ... | provisions the user account -> preparing the access badge | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the user is new, show the onboarding ... | user is new -> show the onboarding tour | **TRUE_BRANCH** | ❌ SEQUENCE | ❌ CONDITION_DEF | No reasoning... |
| The customer places the order. The kitch... | places the order -> receives the ticket | **SEQUENCE** | ✅ SEQUENCE | ❌ PARALLEL | No reasoning... |
| If the visa is approved, stamp the passp... | If rejected -> issue a formal notice | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the policy covers flood damage, initi... | If not -> send a denial letter | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the patient condition is critical, ad... | patient condition is critical -> admit to ICU | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The accountant prepares the tax return w... | prepares the tax return -> reviews the ledger | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the subscription is active, grant acc... | If expired -> redirect to the payment page | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the lab results are inconclusive, req... | results are clear -> proceed to diagnosis | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| The system monitors the CPU usage while ... | monitors the CPU usage -> fan speed adjusts automatically | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the account balance is positive, allo... | account balance is positive -> allow the withdrawal | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the applicant has a criminal record, ... | Otherwise -> proceed to the interview | **FALSE_BRANCH** | ❌ CONDITION_DEF | ✅ FALSE_BRANCH | No reasoning... |
| If the blood sugar is low, give the pati... | If normal -> continue observation | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| The athlete stretches their muscles whil... | stretches their muscles -> explains the strategy | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The heavy machinery is inspected while t... | heavy machinery is inspected -> safety protocols are reviewed | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the queue is full, reject the message... | If space is available -> enqueue the message | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the user has administrative privilege... | user has administrative privileges -> enable the edit button | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the temperature drops below freezing,... | temperature drops below freezing -> turn on the heater | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The pilot checks the instruments while t... | checks the instruments -> communicates with the tower | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The algorithm normalizes the data concur... | normalizes the data -> removal of outliers | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the total weight is over 100kg, arran... | Else -> use a courier service | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the total weight is over 100kg, arran... | total weight is over 100kg -> arrange freight transport | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The backend processes the data stream co... | backend processes the data stream -> frontend updating the dashboard | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the sensor reads toxic gas, shut down... | sensor reads toxic gas -> shut down the valve | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The host prepares the agenda while the a... | prepares the agenda -> attendees join the conference call | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The software installs the updates while ... | installs the updates -> watches the tutorial video | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the user creates a new folder, update... | user creates a new folder -> update the directory tree | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| In the event of a fire alarm, evacuate t... | fire alarm -> evacuate the building | **TRUE_BRANCH** | ❌ SEQUENCE | ❌ CONDITION_DEF | No reasoning... |
| If the user creates a password, hash it ... | user creates a password -> hash it with salt | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the request is from an external IP, b... | request is from an external IP -> block the port | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The editor cuts the scene while the soun... | cuts the scene -> mixes the dialogue | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the humidity is high, enable the dehu... | Else -> do nothing | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the return is within 30 days, issue a... | return is within 30 days -> issue a full refund | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the code passes the linter, merge the... | code fails -> request changes | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the flight is delayed, send an alert ... | Otherwise -> do nothing | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the project is behind schedule, alloc... | project is behind schedule -> allocate more resources | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| In the event of a power failure, activat... | power failure -> activate the UPS | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The baker kneads the dough while the ove... | kneads the dough -> oven preheats | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the traffic is heavy, take the detour... | traffic is heavy -> take the detour | **TRUE_BRANCH** | ❌ SEQUENCE | ❌ CONDITION_DEF | No reasoning... |
| If the water level is low, open the inta... | Else -> close the intake valve | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the customer credit score is above 75... | customer credit score is above 750 -> automatically approve the loan | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the rainfall is heavy, close the floo... | rainfall is light -> keep them open | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| The robot arm picks up the part simultan... | picks up the part -> conveyor belt moves forward | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the warranty is valid, repair the dev... | warranty is valid -> repair the device for free | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the claim amount is under $500, proce... | Else -> require supervisor approval | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the product is out of stock, notify t... | product is out of stock -> notify the customer | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the sensor reads toxic gas, shut down... | If the air is clean -> keep the valve open | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the subscription is active, grant acc... | subscription is active -> grant access | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the temperature exceeds the threshold... | temperature exceeds the threshold -> activate the cooling system | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the stock price hits the limit, execu... | stock price hits the limit -> execute the sell order | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The conductor waves the baton while the ... | waves the baton -> orchestra plays the opening note | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the smoke detector is triggered, soun... | If it is a false positive -> reset the sensor | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| The inventory system deducts the stock. ... | deducts the stock -> schedules the pickup | **SEQUENCE** | ✅ SEQUENCE | ❌ PARALLEL | No reasoning... |
| If the return is within 30 days, issue a... | If not -> issue store credit | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| The marketing team launches the ads whil... | launches the ads -> calls leads | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the file exists, open it in read mode... | file exists -> open it in read mode | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the validation fails, highlight the e... | validation fails -> highlight the error field | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The loan officer checks credit history w... | checks credit history -> verifies employment | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the voltage is unstable, switch to th... | If stable -> remain on the main grid | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the document is signed, file it in th... | document is unsigned -> return it to the sender | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| The lawyer drafts the affidavit whilst t... | drafts the affidavit -> organizes the exhibits | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The satellite unfolds its solar panels w... | unfolds its solar panels -> communicating with the ground station | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the order value is above $1000, apply... | order value is above $1000 -> apply free shipping | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the file size exceeds 10MB, compress ... | Else -> upload as is | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the user is an admin, show the settin... | Else -> hide the settings panel | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the user creates a new folder, update... | user deletes a folder -> remove it from the index | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| When the sensor detects motion, turn on ... | sensor detects motion -> turn on the security lights | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| In case the package is damaged, take a p... | package is damaged -> take a photo | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The artist mixes the paint while the mod... | mixes the paint -> holds the pose | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the humidity is high, enable the dehu... | humidity is high -> enable the dehumidifier | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the temperature drops below freezing,... | If not -> keep the heater off | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the user selects the dark theme, appl... | If light theme -> apply the light CSS | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the user selects 'Express Shipping', ... | user selects 'Express Shipping' -> add a $20 fee | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the code passes the linter, merge the... | code passes the linter -> merge the pull request | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The accountant reconciles the bank state... | reconciles the bank statement -> payroll processing | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the queue is full, reject the message... | queue is full -> reject the message | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the password complexity is low, promp... | Else -> save the credentials | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the project is behind schedule, alloc... | If on schedule -> continue as planned | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| The surgeon makes the incision while the... | makes the incision -> monitors the heart rate | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| In case of a network timeout, retry the ... | network timeout -> retry the connection | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the user is new, show the onboarding ... | If returning -> show the dashboard | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the temperature is above 30 degrees, ... | temperature is above 30 degrees -> turn on the AC | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The server receives the request. The loa... | receives the request -> distributes the traffic | **SEQUENCE** | ✅ SEQUENCE | ❌ PARALLEL | No reasoning... |
| If the cart is empty, show the empty sta... | If items exist -> show the checkout button | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| The student reads the textbook whilst ta... | reads the textbook -> taking summary notes | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The system generates a PDF report whilst... | generates a PDF report -> sending an email summary | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The backend calculates the hash while th... | calculates the hash -> displays the progress bar | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the policy covers flood damage, initi... | policy covers flood damage -> initiate the assessment | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the cart is empty, show the empty sta... | cart is empty -> show the empty state | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the logic gate receives a high signal... | logic gate receives a high signal -> output true | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the KYC verification passes, activate... | If it fails -> freeze the account temporarily | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| The architect drafts the blueprint while... | drafts the blueprint -> calculates the load bearing | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the subscription renews automatically... | If manual -> send a reminder | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the temperature is above 30 degrees, ... | If below -> open the windows | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the user is a premium member, remove ... | Otherwise -> display banner ads | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the candidate passes the coding test,... | If not -> send a regret email | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the vehicle mileage is over 100k, per... | Else -> perform a minor service | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the server load is high, spin up a ne... | server load is high -> spin up a new instance | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the KYC verification passes, activate... | KYC verification passes -> activate the wallet | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The chef prepares the main course at the... | prepares the main course -> preps the salad | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the account balance is positive, allo... | If negative -> charge an overdraft fee | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| While the payment is processing, the sys... | payment is processing -> displays a loading spinner | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the file size exceeds 10MB, compress ... | file size exceeds 10MB -> compress the file | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the interest rate rises, lock in the ... | interest rate rises -> lock in the mortgage | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the validation fails, highlight the e... | If it passes -> submit the form | **FALSE_BRANCH** | ❌ SEQUENCE | ❌ TRUE_BRANCH | No reasoning... |
| If the user selects 'Express Shipping', ... | Else -> apply standard shipping rates | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| The machine washes the bottles and steri... | washes the bottles -> sterilizes the caps | **SEQUENCE** | ✅ SEQUENCE | ❌ PARALLEL | No reasoning... |
| If the database is locked, wait for rele... | Else -> execute the query | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| The student presents the thesis whilst t... | presents the thesis -> evaluates the defense | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the rainfall is heavy, close the floo... | rainfall is heavy -> close the floodgates | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The server logs the error while notifyin... | logs the error -> notifying the admin | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The developer writes the API documentati... | writes the API documentation -> creates test cases | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The sales rep drafts the contract while ... | drafts the contract -> reviews the terms | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| The auditor checks the financial records... | checks the financial records -> prepares the compliance report | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the email is marked as spam, move it ... | Else -> leave it in the inbox | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the server load is high, spin up a ne... | Else -> maintain current capacity | **FALSE_BRANCH** | ❌ SEQUENCE | ✅ FALSE_BRANCH | No reasoning... |
| If the lab results are inconclusive, req... | lab results are inconclusive -> request a re-test | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the applicant has a criminal record, ... | applicant has a criminal record -> reject the application | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| If the claim amount is under $500, proce... | claim amount is under $500 -> process it immediately | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
| The script scrapes the website while the... | scrapes the website -> database indexes the new links | **PARALLEL** | ❌ SEQUENCE | ✅ PARALLEL | No reasoning... |
| If the vehicle mileage is over 100k, per... | vehicle mileage is over 100k -> perform a major service | **TRUE_BRANCH** | ❌ SEQUENCE | ✅ TRUE_BRANCH | No reasoning... |
