import datetime
import os


class FileSender:
    def send(self, incident_id: str, payload: str) -> None:
        os.makedirs("notifications", exist_ok=True)
        now = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"notifications/incident_{incident_id}_{now}.txt"
        with open(filename, "w") as f:
            f.write(payload)
