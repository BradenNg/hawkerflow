import pandas as pd
from sklearn.tree import DecisionTreeClassifier
import joblib

# Load training data
data = pd.read_csv("training_data.csv")

# Sensor inputs
X = pd.get_dummies(
    data[["pm25", "air_velocity", "fan_speed", "route"]]
)

# Correct conditions
y = data["condition"]

# Create the AI model
model = DecisionTreeClassifier(
    max_depth=3,
    random_state=42
)

# Train
model.fit(X, y)

# Save model and feature names together
joblib.dump({
    "model": model,
    "columns": X.columns.tolist()
}, "hawkerflow_ai.joblib")

print("AI training completed!")
