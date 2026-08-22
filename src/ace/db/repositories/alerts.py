from sqlalchemy.orm import Session


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
