#workflows/graph.py

import os
import concurrent.futures
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel


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


def _enhance_visual(scene: dict) -> dict:
  prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a Visual Director Agent. Rewrite short visual descriptions into detailed, cinematic image-generation prompts (specify lighting, lens, mood)."),
    ("user", "Visual: {visual}")
  ])
  chain = prompt | get_llm()
  res = chain.invoke({"visual": scene["visual"]})
  enhanced_scene = scene.copy()

  enhanced_scene["image_prompt"] = extract_text(res).strip()
  return enhanced_scene


def visual_director_agent(state: ReelState) -> ReelState:
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    enhanced_scenes = list(executor.map(_enhance_visual, state["scene_json"]))
  return {"image_prompts": enhanced_scenes}


workflow = StateGraph(ReelState)
workflow.add_node("refiner", prompt_refiner_agent)
workflow.add_node("screenplay", screenplay_agent)
workflow.add_node("planner", scene_planner_agent)
workflow.add_node("visual_director", visual_director_agent)

workflow.set_entry_point("refiner")
workflow.add_edge("refiner", "screenplay")
workflow.add_edge("screenplay", "planner")
workflow.add_edge("planner", "visual_director")
workflow.add_edge("visual_director", END)

memory = MemorySaver()
reel_app = workflow.compile(checkpointer=memory)
