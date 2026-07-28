#workflows/graph.py

import os
import base64
import concurrent.futures
from typing import TypedDict, List, Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from services.image_provider import get_image_provider


class ReelState(TypedDict):
  raw_prompt: str
  duration: int
  style: str
  platform: str
  voice_gender: str
  refined_prompt: str
  creative_brief: Dict[str, Any]
  screenplay: str
  scene_json: List[Dict[str, Any]]
  image_prompts: List[Dict[str, Any]]
  run_dir: str
  dev_mode: str
  is_consistent: bool
  reviewer_feedback: str


_llm_instance = None


def get_llm():
  global _llm_instance
  if _llm_instance is None:
    _llm_instance = ChatGoogleGenerativeAI(
      model="gemini-flash-lite-latest",
      max_retries=3
    )
  return _llm_instance


def check_consistency(state: ReelState) -> Literal["subject_extractor", "screenplay"]:
  if state.get("is_consistent", True):
    return "subject_extractor"
  return "screenplay"


def extract_text(response) -> str:
  """Handles both str content and list-of-blocks content from different Gemini model versions."""
  content = response.content
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    parts = []
    for block in content:
      if isinstance(block, str):
        parts.append(block)
      elif isinstance(block, dict):
        parts.append(block.get("text", ""))
    return "".join(parts)
  return str(content)


def prompt_refiner_agent(state: ReelState) -> ReelState:
  print("[graph] refiner starting...")
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Prompt Refiner Agent. Expand the user's raw prompt into a detailed brief including target audience, tone, pacing, hook, and CTA."),
    ("user", "Raw prompt: {raw_prompt}\nDuration: {duration}s\nStyle: {style}\nPlatform: {platform}")
  ])
  chain = prompt | get_llm()
  response = chain.invoke(state)
  print("[graph] refiner done")
  return {"refined_prompt": extract_text(response)}


def screenplay_agent(state: ReelState) -> ReelState:
  print("[graph] screenplay starting...")

  feedback_context = f"\nREVISION FEEDBACK: {state.get('reviewer_feedback')}" if state.get("reviewer_feedback") else ""

  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Screenplay Agent. Write a script based STRICTLY on the provided Creative Brief (Story Bible). "
     "Do not deviate from the specified analogy, character, or setting. "
     "Write FULL spoken voiceover lines for each beat — complete sentences the narrator will say aloud. "
     "Never use single-word labels or keyword stubs as dialogue."),
    ("user", "Creative Brief: {creative_brief}\nDuration: {duration}s{feedback}")
  ])

  chain = prompt | get_llm()
  response = chain.invoke({**state, "feedback": feedback_context})
  print("[graph] screenplay done")
  return {"screenplay": extract_text(response)}


class Scene(BaseModel):
  scene: int = Field(description="1-based scene index")
  narration: str = Field(
    description=(
      "Complete spoken voiceover sentence for this beat. "
      "8–20 words. This text becomes TTS audio AND subtitles. "
      "Never keywords, labels, or one-word stubs (e.g. not 'Blueprint' or 'Ferrari')."
    )
  )
  summary: str = Field(
    description=(
      "Short beat purpose only (e.g. 'Hook', 'Introduce analogy'). "
      "Must NOT replace or shorten narration."
    )
  )
  visual: str = Field(description="What appears on screen this beat — concrete and filmable")
  duration: int = Field(description="Length of this scene in seconds")
  effect: str = Field(description="Camera/motion effect, e.g. zoom in, pan left")


class SceneList(BaseModel):
  scenes: List[Scene]


def scene_planner_agent(state: ReelState) -> ReelState:
  print("[graph] planner starting...")
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Scene Planner Agent. Convert the screenplay into structured scenes. "
     "PRESERVE information — do not summarize narration into keywords. "
     "Each scene must include: full spoken narration (copied/adapted from the screenplay as a complete sentence), "
     "a short summary (purpose only), visual, duration, and effect. "
     "Narration will be read aloud and shown as subtitles; it must stay a full sentence (8–20 words). "
     "Stay faithful to the Creative Brief (Story Bible)."),
    ("user",
     "Creative Brief (Story Bible): {creative_brief}\n\n"
     "Screenplay:\n{screenplay}\n\n"
     "Total duration must be exactly {duration} seconds.")
  ])
  structured_llm = get_llm().with_structured_output(SceneList)
  chain = prompt | structured_llm
  response = chain.invoke(state)

  scenes = [scene.model_dump() for scene in response.scenes]

  max_scenes = max(3, state["duration"] // 3)
  if len(scenes) > max_scenes:
    scenes = scenes[:max_scenes]

  total_planned = sum(s["duration"] for s in scenes)
  if total_planned != state["duration"] and total_planned > 0:
    factor = state["duration"] / total_planned
    for s in scenes:
      s["duration"] = max(1, round(s["duration"] * factor))

  for s in scenes:
    words = (s.get("narration") or "").split()
    if len(words) < 6:
      print(f"[graph] WARNING short narration on scene {s.get('scene')}: {s.get('narration')!r}")

  print("[graph] planner done")
  return {"scene_json": scenes}


class SceneSubject(BaseModel):
  main_subject: str = Field(description="The concrete object or person in the scene")
  action: str = Field(description="What the subject is doing")
  setting: str = Field(description="Where the scene takes place")
  emotion: str = Field(description="The overarching mood")


def _extract_subject(scene: dict, prompt: ChatPromptTemplate, structured_llm) -> dict:
  scene = scene.copy()
  if not scene.get("narration"):
    scene["narration"] = scene.get("voice") or ""
  scene.setdefault("summary", "")
  chain = prompt | structured_llm
  subject_data = chain.invoke(scene)
  scene["subject_data"] = subject_data.model_dump()
  return scene


def subject_extractor_agent(state: ReelState) -> ReelState:
  print("[graph] subject_extractor starting...")
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "Extract the literal, concrete subjects from the scene description. Ignore abstract concepts. "
     "Use the narration and visual together — do not discard the narration."),
    ("user",
     "Narration (spoken line): {narration}\n"
     "Beat summary: {summary}\n"
     "Visual concept: {visual}")
  ])
  structured_llm = get_llm().with_structured_output(SceneSubject)

  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(_extract_subject, scene, prompt, structured_llm) for scene in state["scene_json"]]
    updated_scenes = [f.result() for f in futures]

  print("[graph] subject_extractor done")
  return {"scene_json": updated_scenes}


class Concept(BaseModel):
  analogy: str = Field(description="The core metaphor or analogy")
  main_character: str = Field(description="The specific subject/character")
  setting: str = Field(description="The primary visual location")
  visual_style: str = Field(description="The art direction")
  originality_score: int = Field(description="Score 1-5 for how surprising/novel it is")
  visual_potential: int = Field(description="Score 1-5 for how good it will look")


class ConceptList(BaseModel):
  concepts: List[Concept]


class ConsistencyCheck(BaseModel):
  is_consistent: bool = Field(description="True if the scenes perfectly match the creative brief")
  feedback: str = Field(description="Critique if inconsistent, or empty if perfect")


def creative_director_agent(state: ReelState) -> ReelState:
  print("[graph] creative_director starting...")
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Creative Director. Generate 5 wildly different, highly original concepts to explain the user's prompt. "
     "Hard avoid (overused): blueprint, recipe, house blueprint, cars/Ferrari as default OOP metaphor, basic office. "
     "Prefer surprising, visual worlds when they fit (e.g. Pokemon, Minecraft, Lego, Iron Man suit shop, clone factory, magic spell). "
     "Prioritize visual storytelling, surprise, and humor. Format as a strict list of 5 concepts."),
    ("user", "Topic: {raw_prompt}\nTarget Style: {style}")
  ])

  structured_llm = get_llm().with_structured_output(ConceptList)
  response = (prompt | structured_llm).invoke(state)

  # Deterministic Selection: Rank by combined score
  sorted_concepts = sorted(
    response.concepts,
    key=lambda x: x.originality_score + x.visual_potential,
    reverse=True
  )
  best_concept = sorted_concepts[0].model_dump()

  print(f"[graph] selected concept: {best_concept['analogy']}")
  return {"creative_brief": best_concept}


def consistency_reviewer_agent(state: ReelState) -> ReelState:
  print("[graph] reviewer starting...")
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Continuity Director. Compare the generated scenes against the Creative Brief (Story Bible). "
     "If the scenes drift from the analogy, introduce unrelated elements, or break continuity, reject it (is_consistent = false) and provide strict feedback. "
     "Also reject if any scene narration is missing, a single keyword, or not a complete spoken sentence."),
    ("user", "Creative Brief:\n{creative_brief}\n\nGenerated Scenes:\n{scene_json}")
  ])

  structured_llm = get_llm().with_structured_output(ConsistencyCheck)
  review = (prompt | structured_llm).invoke(state)

  print(f"[graph] reviewer decision: Consistent={review.is_consistent}")
  return {
    "is_consistent": review.is_consistent,
    "reviewer_feedback": review.feedback
  }


class StructuredPrompt(BaseModel):
  subject: str
  action: str
  background: str
  camera: str
  style_keywords: str
  lighting: str


def _build_image_prompt(scene: dict, style: str) -> dict:
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Visual Director Agent for a text-to-image model with a strict "
     "77-token limit. Using the extracted subject data, produce a strict image "
     "generation template. The image MUST clearly depict the literal subject/action/"
     "setting given — do not invent unrelated symbolism, characters, or genre "
     "aesthetics (e.g. don't turn a technical/educational topic into cyberpunk/sci-fi "
     "imagery) unless the subject data explicitly calls for it. "
     "Style requested: {style}. Match it accurately (e.g. 'Educational' = flat vector "
     "illustration, 'Cinematic' = 35mm shallow depth of field)."),
    ("user", "Subject data: {subject_data}")
  ])
  structured_llm = get_llm().with_structured_output(StructuredPrompt)
  res = (prompt | structured_llm).invoke({
    "style": style,
    "subject_data": scene.get("subject_data", {"main_subject": scene["visual"]})
  })

  final_prompt = (
    f"{res.subject}, {res.action}, {res.background}, {res.camera}, "
    f"{res.style_keywords}, {res.lighting}, highly detailed, masterpiece"
  )

  enhanced_scene = scene.copy()
  enhanced_scene["image_prompt"] = " ".join(final_prompt.split()[:60])
  return enhanced_scene


def visual_director_agent(state: ReelState) -> ReelState:
  print("[graph] visual_director starting...")
  style = state["style"]
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(_build_image_prompt, scene, style) for scene in state["scene_json"]]
    enhanced_scenes = [f.result() for f in futures]

  print("[graph] visual_director done")
  return {"image_prompts": enhanced_scenes}


def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')


def image_generation_and_critic_agent(state: ReelState) -> ReelState:
  print("[graph] image_generation_and_critic starting...")
  mode = state.get("dev_mode", "production")
  provider = get_image_provider(mode)
  vision_llm = get_llm()
  run_dir = state.get("run_dir", "assets/temp")

  candidates_count = 1 if mode in ["mock", "fast"] else 3

  for scene in state["image_prompts"]:
    candidates = []
    for i in range(candidates_count):
      path = provider.generate(scene["image_prompt"], run_dir, f"scene_{scene['scene']}_cand_{i}")
      candidates.append(path)

    if candidates_count == 1:
      best_img = candidates[0]
    else:
      messages = [
        HumanMessage(content=[
          {"type": "text",
           "text": f"Narration: {scene.get('narration') or scene.get('voice')}\nWhich of these 3 images best matches the narration and is visually clearest? Return ONLY the number 1, 2, or 3."},
          {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(candidates[0])}"}},
          {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(candidates[1])}"}},
          {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(candidates[2])}"}}
        ])
      ]

      try:
        choice = int(extract_text(vision_llm.invoke(messages)).strip())
        best_img = candidates[choice - 1 if 1 <= choice <= 3 else 0]
      except Exception:
        best_img = candidates[0]

    final_path = os.path.join(run_dir, "images", f"scene_{scene['scene']}.png")
    if os.path.exists(final_path):
      os.remove(final_path)
    os.rename(best_img, final_path)

    for c in candidates:
      if os.path.exists(c) and c != best_img:
        os.remove(c)

  print("[graph] image_generation_and_critic done")
  return state


workflow = StateGraph(ReelState)

workflow.add_node("creative_director", creative_director_agent)
workflow.add_node("screenplay", screenplay_agent)
workflow.add_node("planner", scene_planner_agent)
workflow.add_node("reviewer", consistency_reviewer_agent)
workflow.add_node("subject_extractor", subject_extractor_agent)
workflow.add_node("visual_director", visual_director_agent)
workflow.add_node("image_production", image_generation_and_critic_agent)

workflow.set_entry_point("creative_director")
workflow.add_edge("creative_director", "screenplay")
workflow.add_edge("screenplay", "planner")
workflow.add_edge("planner", "reviewer")

workflow.add_conditional_edges(
    "reviewer",
    check_consistency
)

workflow.add_edge("subject_extractor", "visual_director")
workflow.add_edge("visual_director", "image_production")
workflow.add_edge("image_production", END)

memory = MemorySaver()
reel_app = workflow.compile(checkpointer=memory)
