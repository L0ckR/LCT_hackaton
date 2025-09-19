from sqlalchemy.orm import Session
from app.models.review import Review


def fake_cluster(db: Session):
    reviews = db.query(Review).all()
    clusters = {}
    for review in reviews:
        clusters.setdefault(review.product or "unknown", []).append(review.id)
    return {"clusters": [{"name": name, "review_ids": ids} for name, ids in clusters.items()]}
