from fastapi import FastAPI
import torch
from transformers import pipeline

from ray import serve
from ray.serve.handle import DeploymentHandle


app = FastAPI()


@serve.deployment(num_replicas=1)
@serve.ingress(app)
class APIIngress:
    def __init__(self, bert_model_handle: DeploymentHandle) -> None:
        self.handle = bert_model_handle

    @app.get("/classify")
    async def classify(self, sentence: str):
        return await self.handle.classify.remote(sentence)


@serve.deployment(
    ray_actor_options={"num_gpus": 1},
    autoscaling_config={"min_replicas": 0, "max_replicas": 2},
)
class BertModel:
    def __init__(self):
        self.classifier = pipeline(
            "text-classification",
            model="lockR/xlm-roberta-finance-multi-label-classification",
            framework="pt",
            top_k=None,
            # Transformers requires you to pass device with index
            device=torch.device("cuda:0"),
        )

    def classify(self, sentence: str):
        return self.classifier(sentence)


entrypoint = APIIngress.bind(BertModel.bind())
