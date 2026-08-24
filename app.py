from flask import Flask,render_template,request,redirect,session,flash,jsonify
import sqlite3
from datetime import datetime

app=Flask(__name__)
app.secret_key="apexcare-demo-secret"
DB="database.db"

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS patients(
      id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL, age INTEGER NOT NULL, gender TEXT NOT NULL,
      phone TEXT NOT NULL, email TEXT, emergency INTEGER DEFAULT 0,
      status TEXT DEFAULT 'in_queue', created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS vitals(
      id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id TEXT NOT NULL,
      systolic INTEGER,diastolic INTEGER,heart_rate INTEGER,spo2 INTEGER,
      temperature REAL,respiratory_rate INTEGER,consciousness TEXT,
      priority TEXT,score INTEGER,recorded_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS alerts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id TEXT NOT NULL,
      alert_type TEXT NOT NULL,message TEXT NOT NULL,
      created_at TEXT NOT NULL,resolved INTEGER DEFAULT 0)""")
    try:c.execute("ALTER TABLE patients ADD COLUMN status TEXT DEFAULT 'in_queue'")
    except sqlite3.OperationalError:pass
    c.commit();c.close()

def priority(sbp,hr,spo2,temp,rr,con):
    score=0
    if spo2<90:score+=5
    elif spo2<94:score+=3
    if hr<50 or hr>120:score+=3
    elif hr>100:score+=1
    if sbp<90 or sbp>180:score+=3
    elif sbp>160:score+=1
    if temp>=39 or temp<35:score+=3
    elif temp>=38:score+=1
    if rr<8 or rr>30:score+=3
    elif rr>22:score+=1
    if con=="Unresponsive":score+=5
    elif con=="Confused":score+=4
    elif con=="Drowsy":score+=2
    return ("HIGH",score) if score>=7 else (("MEDIUM",score) if score>=3 else ("LOW",score))

def patients():
    c=db()
    rows=c.execute("""SELECT p.*,v.systolic,v.diastolic,v.heart_rate,v.spo2,v.temperature,
      v.respiratory_rate,v.consciousness,v.priority,v.score,v.recorded_at
      FROM patients p LEFT JOIN vitals v ON v.id=(SELECT id FROM vitals
      WHERE patient_id=p.patient_id ORDER BY id DESC LIMIT 1)
      WHERE p.status='in_queue'
      ORDER BY CASE WHEN p.emergency=1 THEN 0 WHEN v.priority='HIGH' THEN 1
      WHEN v.priority='MEDIUM' THEN 2 WHEN v.priority='LOW' THEN 3 ELSE 4 END,
      v.recorded_at DESC""").fetchall()
    c.close();return rows

def stats():
    c=db()
    out={}
    for k,q in {
      "total":"SELECT COUNT(*) n FROM patients",
      "queue":"SELECT COUNT(*) n FROM patients WHERE status='in_queue'",
      "checked":"SELECT COUNT(*) n FROM patients WHERE status='checked'",
      "left":"SELECT COUNT(*) n FROM patients WHERE status='left'",
      "high":"""SELECT COUNT(*) n FROM patients p JOIN vitals v ON v.id=(SELECT id FROM vitals
        WHERE patient_id=p.patient_id ORDER BY id DESC LIMIT 1)
        WHERE p.status='in_queue' AND (v.priority='HIGH' OR p.emergency=1)""",
      "medium":"""SELECT COUNT(*) n FROM patients p JOIN vitals v ON v.id=(SELECT id FROM vitals
        WHERE patient_id=p.patient_id ORDER BY id DESC LIMIT 1)
        WHERE p.status='in_queue' AND v.priority='MEDIUM'""",
      "low":"""SELECT COUNT(*) n FROM patients p JOIN vitals v ON v.id=(SELECT id FROM vitals
        WHERE patient_id=p.patient_id ORDER BY id DESC LIMIT 1)
        WHERE p.status='in_queue' AND v.priority='LOW'"""
    }.items():out[k]=c.execute(q).fetchone()["n"]
    c.close();return out

def panic_count():
    c=db();n=c.execute("SELECT COUNT(*) n FROM alerts WHERE resolved=0").fetchone()["n"];c.close();return n

@app.route("/")
def home():return render_template("home.html")
@app.route("/about")
def about():return render_template("about.html")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        role=request.form.get("role","")
        if role=="nurse" and request.form.get("username","").lower()=="nurse" and request.form.get("password")=="1234":
            session.clear();session["role"]="nurse";return redirect("/nurse")
        if role=="doctor" and request.form.get("username","").lower()=="doctor" and request.form.get("password")=="1234":
            session.clear();session["role"]="doctor";return redirect("/doctor")
        if role=="patient":
            c=db();p=c.execute("SELECT * FROM patients WHERE lower(name)=lower(?) AND phone=? AND status!='left'",
              (request.form.get("name","").strip(),request.form.get("phone","").strip())).fetchone();c.close()
            if p:
                session.clear();session["pending_patient"]=p["patient_id"];return render_template("otp.html",name=p["name"])
        flash("Login details are incorrect.","error")
    return render_template("login.html")

@app.route("/verify-otp",methods=["POST"])
def verify():
    if request.form.get("otp")=="1234" and session.get("pending_patient"):
        session["role"]="patient";session["patient_id"]=session.pop("pending_patient");return redirect("/patient")
    flash("Incorrect OTP. Demo OTP is 1234.","error");return render_template("otp.html",name="Patient")

@app.route("/logout")
def logout():session.clear();return redirect("/")

@app.route("/nurse",methods=["GET","POST"])
def nurse():
    if session.get("role")!="nurse":return redirect("/login")
    if request.method=="POST":
        pid=request.form.get("patient_id","").strip().upper() or "APX"+datetime.now().strftime("%y%m%d%H%M%S")
        c=db()
        try:
            c.execute("""INSERT INTO patients(patient_id,name,age,gender,phone,email,emergency,status,created_at)
              VALUES(?,?,?,?,?,?,0,'in_queue',?)""",(pid,request.form["name"],int(request.form["age"]),
              request.form["gender"],request.form["phone"],request.form.get("email",""),datetime.now().isoformat(timespec="seconds")))
            c.commit();flash("Patient registered: "+pid,"success")
        except sqlite3.IntegrityError:flash("Patient ID already exists.","error")
        c.close()
    return render_template("nurse.html",patients=patients(),stats=stats(),panic_count=panic_count())

@app.route("/vitals",methods=["POST"])
def vitals():
    if session.get("role")!="nurse":return redirect("/login")
    pid=request.form["patient_id"].upper()
    try:
        sbp=int(request.form["systolic"]);dbp=int(request.form["diastolic"]);hr=int(request.form["heart_rate"])
        spo2=int(request.form["spo2"]);temp=float(request.form["temperature"]);rr=int(request.form["respiratory_rate"])
        con=request.form["consciousness"]
    except(ValueError,KeyError):
        flash("Invalid vital values.","error");return redirect("/nurse")
    c=db()
    if not c.execute("SELECT 1 FROM patients WHERE patient_id=?",(pid,)).fetchone():
        c.close();flash("Patient not found.","error");return redirect("/nurse")
    pr,sc=priority(sbp,hr,spo2,temp,rr,con)
    c.execute("""INSERT INTO vitals(patient_id,systolic,diastolic,heart_rate,spo2,temperature,
      respiratory_rate,consciousness,priority,score,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
      (pid,sbp,dbp,hr,spo2,temp,rr,con,pr,sc,datetime.now().isoformat(timespec="seconds")))
    c.commit();c.close();flash(f"{pid} priority updated to {pr}.","error" if pr=="HIGH" else "success")
    return redirect("/nurse")

@app.route("/status/<pid>/<action>",methods=["POST"])
def status(pid,action):
    if session.get("role") not in ("nurse","doctor") and not(session.get("role")=="patient" and session.get("patient_id")==pid):
        return redirect("/login")
    new={"check":"checked","remove":"left","exit":"left"}.get(action)
    if not new:return redirect("/")
    c=db();c.execute("UPDATE patients SET status=? WHERE patient_id=?",(new,pid));c.commit();c.close()
    return redirect("/nurse" if session["role"]=="nurse" else "/doctor" if session["role"]=="doctor" else "/patient")

@app.route("/doctor")
def doctor():
    if session.get("role")!="doctor":return redirect("/login")
    return render_template("doctor.html",patients=patients(),stats=stats())

@app.route("/patient")
def patient():
    if session.get("role")!="patient":return redirect("/login")
    pid=session["patient_id"];c=db()
    p=c.execute("""SELECT p.*,v.systolic,v.diastolic,v.heart_rate,v.spo2,v.temperature,
      v.respiratory_rate,v.consciousness,v.recorded_at,v.score FROM patients p
      LEFT JOIN vitals v ON v.id=(SELECT id FROM vitals WHERE patient_id=p.patient_id
      ORDER BY id DESC LIMIT 1) WHERE p.patient_id=?""",(pid,)).fetchone()
    ahead=[]
    if p and p["score"] is not None:
        ahead=c.execute("""SELECT age FROM patients p JOIN vitals v ON v.id=(SELECT id FROM vitals
          WHERE patient_id=p.patient_id ORDER BY id DESC LIMIT 1)
          WHERE p.status='in_queue' AND v.score>? ORDER BY v.score DESC""",(p["score"],)).fetchall()
    c.close();return render_template("patient.html",patient=p,ahead=ahead)

@app.route("/panic",methods=["POST"])
def panic():
    if session.get("role")!="patient":return redirect("/login")
    c=db();c.execute("INSERT INTO alerts(patient_id,alert_type,message,created_at) VALUES(?,?,?,?)",
      (session["patient_id"],"PANIC","Patient pressed the panic button.",datetime.now().isoformat(timespec="seconds")))
    c.commit();c.close();flash("Panic alert sent to the nurse.","success");return redirect("/patient")

@app.route("/panic-alerts")
def panic_alerts():
    if session.get("role")!="nurse":return jsonify({"error":"Unauthorized"}),401
    c=db();r=c.execute("""SELECT a.id,a.patient_id,a.message,a.created_at,p.name FROM alerts a
      JOIN patients p ON p.patient_id=a.patient_id WHERE a.resolved=0 ORDER BY a.id DESC""").fetchall();c.close()
    return jsonify([dict(x) for x in r])

@app.route("/resolve-alert/<int:aid>",methods=["POST"])
def resolve(aid):
    if session.get("role")!="nurse":return redirect("/login")
    c=db();c.execute("UPDATE alerts SET resolved=1 WHERE id=?",(aid,));c.commit();c.close();return redirect("/nurse")

@app.route("/emergency",methods=["GET","POST"])
def emergency():
    if request.method=="POST":
        pid="EMG"+datetime.now().strftime("%y%m%d%H%M%S");c=db()
        c.execute("""INSERT INTO patients(patient_id,name,age,gender,phone,email,emergency,status,created_at)
          VALUES(?,?,?,?,?,'',1,'in_queue',?)""",(pid,request.form["name"],int(request.form["age"]),
          request.form["gender"],request.form.get("phone",""),datetime.now().isoformat(timespec="seconds")))
        c.commit();c.close();return render_template("emergency_success.html",patient_id=pid)
    return render_template("emergency.html")

if __name__=="__main__":
    init_db();app.run(host="0.0.0.0",port=5000,debug=True)
