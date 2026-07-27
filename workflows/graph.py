#workflows/graph.py

import os
import base64
import concurrent.futures
from typing import TypedDict, List, Dict, Any
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
  screenplay: str
  scene_json: List[Dict[str, Any]]
  image_prompts: List[Dict[str, Any]]
  run_dir: str
  dev_mode: str


_llm_instance = None


def get_llm():
  global _llm_instance
  if _llm_instance is None:
    _llm_instance = ChatGoogleGenerativeAI(
      model="gemini-flash-lite-latest",
      max_retries=3
    )
  return _llm_instance


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
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Screenplay Agent. Break the refined brief down into scenes. Include narration text, visual description, camera angle, and transition for each."),
    ("user", "Brief: {refined_prompt}")
  ])
  chain = prompt | get_llm()
  response = chain.invoke(state)
  print("[graph] screenplay done")
  return {"screenplay": extract_text(response)}


class Scene(BaseModel):
  scene: int
  duration: int
  visual: str
  voice: str
  effect: str


class SceneList(BaseModel):
  scenes: List[Scene]


def scene_planner_agent(state: ReelState) -> ReelState:
  print("[graph] planner starting...")
  prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a Scene Planner Agent. Convert the screenplay into a strict JSON array of scenes."),
    ("user", "Screenplay: {screenplay}\nMake sure total duration is exactly {duration} seconds.")
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

  print("[graph] planner done")
  return {"scene_json": scenes}


class SceneSubject(BaseModel):
  main_subject: str = Field(description="The concrete object or person in the scene")
  action: str = Field(description="What the subject is doing")
  setting: str = Field(description="Where the scene takes place")
  emotion: str = Field(description="The overarching mood")


def _extract_subject(scene: dict, prompt: ChatPromptTemplate, structured_llm) -> dict:
  chain = prompt | structured_llm
  subject_data = chain.invoke(scene)
  scene = scene.copy()
  scene["subject_data"] = subject_data.model_dump()
  return scene


def subject_extractor_agent(state: ReelState) -> ReelState:
  print("[graph] subject_extractor starting...")
  prompt = ChatPromptTemplate.from_messages([
    ("system", "Extract the literal, concrete subjects from the scene description. Ignore abstract concepts."),
    ("user", "Scene script: {voice}\nVisual concept: {visual}")
  ])
  structured_llm = get_llm().with_structured_output(SceneSubject)

  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(_extract_subject, scene, prompt, structured_llm) for scene in state["scene_json"]]
    updated_scenes = [f.result() for f in futures]

  print("[graph] subject_extractor done")
  return {"scene_json": updated_scenes}


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
           "text": f"Narration: {scene['voice']}\nWhich of these 3 images best matches the narration and is visually clearest? Return ONLY the number 1, 2, or 3."},
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
workflow.add_node("refiner", prompt_refiner_agent)
workflow.add_node("screenplay", screenplay_agent)
workflow.add_node("planner", scene_planner_agent)
workflow.add_node("subject_extractor", subject_extractor_agent)
workflow.add_node("visual_director", visual_director_agent)
workflow.add_node("image_production", image_generation_and_critic_agent)

workflow.set_entry_point("refiner")
workflow.add_edge("refiner", "screenplay")
workflow.add_edge("screenplay", "planner")
workflow.add_edge("planner", "subject_extractor")
workflow.add_edge("subject_extractor", "visual_director")
workflow.add_edge("visual_director", "image_production")
workflow.add_edge("image_production", END)

memory = MemorySaver()
reel_app = workflow.compile(checkpointer=memory)
