from sqlalchemy.orm import Session


class ComponentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
