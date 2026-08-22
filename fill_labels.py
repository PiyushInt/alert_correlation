import csv

alerts = {
    "P_0": "CartDown",
    "P_1": "CartDown",
    "P_2": "CartDown",
    "B_3": "FrontendDown",
    "P_4": "CartDown",
    "P_5": "CartDown",
    "B_6": "CartEndpointDown",
    "P_7": "CartDown",
}

with open("estate/captures/labels/kill_service.csv") as f:
    reader = csv.reader(f)
    rows = list(reader)

for row in rows[1:]:
    a1 = row[0]
    a2 = row[1]
    name1 = alerts[a1]
    name2 = alerts[a2]

    if name1 == name2:
        row[2] = "N"
    else:
        row[2] = "Y"

with open("estate/captures/labels/kill_service.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(rows)
