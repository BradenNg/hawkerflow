import pandas as pd
import joblib

saved = joblib.load("hawkerflow_ai.joblib")

model = saved["model"]
columns = saved["columns"]

# Example sensor reading
reading = pd.DataFrame([{
    "pm25": 2,
    "air_velocity": 100,
    "fan_speed": 40,
    "route": "A"
}])

X = pd.get_dummies(reading)
X = X.reindex(columns=columns, fill_value=0)

prediction = model.predict(X)[0]

print("Predicted condition:", prediction)
