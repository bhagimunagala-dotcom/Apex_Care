APEXCARE COMPLETED
Run:
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
Open http://127.0.0.1:5000

Demo:
Nurse: nurse / 1234
Doctor: doctor / 1234
Patient OTP: 1234

Patient login: name + phone -> OTP.
Doctor Check, Nurse Remove, Patient Exit.
Panic button creates a nurse alert.
No automatic 30-second refresh.
