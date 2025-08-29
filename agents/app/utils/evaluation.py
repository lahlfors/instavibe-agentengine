# agents/app/utils/evaluation.py
import logging
from vertexai.preview.evaluation import EvalTask
from agents.app.common.types import Evaluation

def evaluate_rag(
    context: str,
    response: str,
    question: str,
    rag_type: str,
) -> Evaluation:
    """
    Evaluates the quality of a RAG (Retrieval-Augmented Generation) response.

    Args:
        context: The context provided to the model.
        response: The model's response.
        question: The question asked to the model.
        rag_type: The type of RAG evaluation.

    Returns:
        An Evaluation object containing the evaluation results.
    """
    logging.info(f"Starting RAG evaluation of type: {rag_type}")

    eval_task = EvalTask(
        dataset=[{"context": context, "question": question}],
        metrics=["summarization_quality"],
    )

    result = eval_task.evaluate(
        instance_display_name="rag_evaluation",
    )

    logging.info(f"RAG evaluation completed. Result: {result}")

    return Evaluation(
        rag_type=rag_type,
        retrieval_quality=result.metrics["retrieval_quality"],
        quality=result.metrics["quality"],
        tool_code=result.tool_code,
    )
