from sqlalchemy.orm import Session


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
