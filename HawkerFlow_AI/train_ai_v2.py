import pandas as pd
import joblib

from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# STEP 1: Load simulated data
data = pd.read_csv("simulated_data.csv")

print("Total readings:", len(data))

# STEP 2: Prepare sensor inputs
X = pd.get_dummies(
    data[["temperature", "air_velocity", "fan_speed", "route"]]
)

# Two separate predictions
y_cooking = data["cooking"]
y_blocked = data["blocked"]

# STEP 3: Split into training and testing data
(
    X_train, X_test,
    cooking_train, cooking_test,
    blocked_train, blocked_test
) = train_test_split(
    X,
    y_cooking,
    y_blocked,
    test_size=0.2,
    random_state=42,
    stratify=(
        y_cooking.astype(str) +
        y_blocked.astype(str)
    )
)

# STEP 4: Create the AI models
cooking_ai = DecisionTreeClassifier(
    max_depth=5,
    random_state=42
)

blockage_ai = DecisionTreeClassifier(
    max_depth=5,
    random_state=42
)

# STEP 5: Train the AI models
cooking_ai.fit(X_train, cooking_train)
blockage_ai.fit(X_train, blocked_train)

print("\nBoth AI models trained successfully!")

# STEP 6: Test the models
cooking_predictions = cooking_ai.predict(X_test)
blockage_predictions = blockage_ai.predict(X_test)

print("\n--- COOKING DETECTION ---")
print("Accuracy:", accuracy_score(
    cooking_test, cooking_predictions
))
print(classification_report(
    cooking_test, cooking_predictions,
    zero_division=0
))

print("\n--- FILTER BLOCKAGE DETECTION ---")
print("Accuracy:", accuracy_score(
    blocked_test, blockage_predictions
))
print(classification_report(
    blocked_test, blockage_predictions,
    zero_division=0
))

# STEP 7: Save the trained models
joblib.dump({
    "cooking_model": cooking_ai,
    "blocked_model": blockage_ai,
    "columns": X.columns.tolist()
}, "hawkerflow_ai_v2.joblib")

print("\nAI models saved successfully!")
