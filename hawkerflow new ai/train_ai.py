
import pandas as pd
import joblib

from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)

# Load simulated pressure dataset
data = pd.read_csv("simulated_data.csv")

# AI inputs: pressure difference, fan speed, route
X = pd.get_dummies(
    data[["delta_pressure", "fan_speed", "route"]]
)

# AI target: blocked or not blocked
y = data["blocked"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# Train blockage AI
model = DecisionTreeClassifier(
    max_depth=5,
    min_samples_leaf=10,
    random_state=42
)

model.fit(X_train, y_train)

# Test
predictions = model.predict(X_test)

print("\nFILTER BLOCKAGE AI RESULTS")
print("Accuracy:", accuracy_score(y_test, predictions))
print(classification_report(
    y_test, predictions, zero_division=0
))
print("Confusion matrix:")
print(confusion_matrix(y_test, predictions))

# Save model
joblib.dump({
    "model": model,
    "columns": X.columns.tolist()
}, "hawkerflow_ai.joblib")

print("\nAI model saved successfully!")
print("WARNING: Results are based on synthetic data only.")
