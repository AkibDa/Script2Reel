#workflows/graph.py

import os
import json
import base64
import concurrent.futures
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from services.image_provider import LocalSDXLProvider


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
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Prompt Refiner Agent. Expand the user's raw prompt into a detailed brief including target audience, tone, pacing, hook, and CTA."),
    ("user", "Raw prompt: {raw_prompt}\nDuration: {duration}s\nStyle: {style}\nPlatform: {platform}")
  ])
  chain = prompt | get_llm()
  response = chain.invoke(state)
  return {"refined_prompt": extract_text(response)}


def screenplay_agent(state: ReelState) -> ReelState:
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Screenplay Agent. Break the refined brief down into scenes. Include narration text, visual description, camera angle, and transition for each."),
    ("user", "Brief: {refined_prompt}")
  ])
  chain = prompt | get_llm()
  response = chain.invoke(state)
  return {"screenplay": extract_text(response)}


class SceneSubject(BaseModel):
  main_subject: str = Field(description="The concrete object or person in the scene")
  action: str = Field(description="What the subject is doing")
  setting: str = Field(description="Where the scene takes place")
  emotion: str = Field(description="The overarching mood")


def subject_extractor_agent(state: ReelState) -> ReelState:
  prompt = ChatPromptTemplate.from_messages([
    ("system", "Extract the literal, concrete subjects from the scene description. Ignore abstract concepts."),
    ("user", "Scene script: {voice}\nVisual concept: {visual}")
  ])
  structured_llm = get_llm().with_structured_output(SceneSubject)

  updated_scenes = []
  for scene in state["scene_json"]:
    chain = prompt | structured_llm
    subject_data = chain.invoke(scene)
    scene["subject_data"] = subject_data.model_dump()
    updated_scenes.append(scene)

  return {"scene_json": updated_scenes}


class StructuredPrompt(BaseModel):
  subject: str
  action: str
  background: str
  camera: str
  style_keywords: str
  lighting: str


def visual_director_agent(state: ReelState) -> ReelState:
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Visual Director. Convert the subject data into a strict image generation template. "
     "Style requested: {style}. Match the style accurately (e.g., 'Educational Explainer' = flat vector illustration, "
     "'Cinematic' = 35mm shallow depth of field)."),
    ("user", "Subject Data: {subject_data}")
  ])
  structured_llm = get_llm().with_structured_output(StructuredPrompt)

  enhanced_scenes = []
  for scene in state["scene_json"]:
    res = (prompt | structured_llm).invoke({"style": state["style"], "subject_data": scene["subject_data"]})

    # Format into a dense comma-separated string for SDXL
    final_prompt = (
      f"{res.subject}, {res.action}, {res.background}, {res.camera}, "
      f"{res.style_keywords}, {res.lighting}, highly detailed, masterpiece"
    )
    scene["image_prompt"] = final_prompt
    enhanced_scenes.append(scene)

  return {"image_prompts": enhanced_scenes}


class Scene(BaseModel):
  scene: int
  duration: int
  visual: str
  voice: str
  effect: str


class SceneList(BaseModel):
  scenes: List[Scene]


def scene_planner_agent(state: ReelState) -> ReelState:
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

  return {"scene_json": scenes}


def _enhance_visual(scene: dict, style: str) -> dict:
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Visual Director Agent for a text-to-image model with a strict "
     "77-token limit. Rewrite the visual description into a concise, "
     "literal, comma-separated image prompt. "
     "The image MUST clearly depict the actual subject described — do not invent "
     "unrelated symbolism, characters, or genre aesthetics (e.g. don't turn a "
     "technical/educational topic into cyberpunk/sci-fi imagery) unless the scene "
     "explicitly calls for it. Style should match: {style}. "
     "No markdown, no headers, no full sentences, no bold text. "
     "Maximum 60 words. Output ONLY the prompt, nothing else."),
    ("user", "Visual: {visual}")
  ])
  chain = prompt | get_llm()
  res = chain.invoke({"visual": scene["visual"], "style": style})
  enhanced_scene = scene.copy()

  text = extract_text(res).strip()
  enhanced_scene["image_prompt"] = " ".join(text.split()[:60])
  return enhanced_scene


def visual_director_agent(state: ReelState) -> ReelState:
  style = state["style"]
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(_enhance_visual, scene, style) for scene in state["scene_json"]]
    enhanced_scenes = [f.result() for f in futures]
  return {"image_prompts": enhanced_scenes}

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')


def image_generation_and_critic_agent(state: ReelState) -> ReelState:
  provider = LocalSDXLProvider()
  vision_llm = get_llm()
  run_dir = state.get("run_dir", "assets/temp")

  for scene in state["image_prompts"]:
    candidates = []
    for i in range(3):
      path = provider.generate(scene["image_prompt"], run_dir, f"scene_{scene['scene']}_cand_{i}")
      candidates.append(path)

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
      choice = int(vision_llm.invoke(messages).content.strip())
      best_img = candidates[choice - 1 if 1 <= choice <= 3 else 0]
    except:
      best_img = candidates[0]

    final_path = os.path.join(run_dir, "images", f"scene_{scene['scene']}.png")
    os.rename(best_img, final_path)

    for c in candidates:
      if os.path.exists(c): os.remove(c)

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
