import streamlit as st
import os
import sys
import importlib
import core.memory
import core.agent
import tools.research_tools
import tools.excel_tools
import tools.ppt_tools
import tools.dcf_tools
import tools.social_media_tools
import tools.deep_research_tools

importlib.reload(core.memory)
importlib.reload(core.agent)
importlib.reload(tools.research_tools)
importlib.reload(tools.excel_tools)
importlib.reload(tools.ppt_tools)
importlib.reload(tools.dcf_tools)
importlib.reload(tools.social_media_tools)
importlib.reload(tools.deep_research_tools)

from dotenv import load_dotenv

# Ensure the DB paths and tools are available
from core.agent import TradingFloor
from core.memory import get_conversation_history, get_assumptions, get_or_create_project, get_tracked_files, get_all_projects, delete_project
from tools.research_tools import get_research_tools
from tools.excel_tools import get_excel_tools
from tools.ppt_tools import get_ppt_tools
from tools.dcf_tools import get_dcf_tools
from tools.social_media_tools import get_social_media_tools
from tools.deep_research_tools import get_deep_research_tools
import streamlit.components.v1 as components
import json

load_dotenv() # Load environment variables, expecting GEMINI_API_KEY

st.set_page_config(page_title="AI Hivemind/Swarm", page_icon="🐝", layout="wide")

# Inject custom CSS
with open("assets/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

st.title("🐝 AI Hivemind/Swarm")
st.caption("M&A | LBO | IPO | Debt Structuring - Powered by Gemini")

# Initialize Session State
if "project_name" not in st.session_state:
    st.session_state["project_name"] = "Project Alpha"
    
if "project_id" not in st.session_state:
    st.session_state["project_id"] = get_or_create_project(st.session_state["project_name"])
    
if "swarm_mode" not in st.session_state:
    st.session_state["swarm_mode"] = "Banking Team (Default)"

# Recreate agent every run to ensure latest code is used and to avoid stale object errors
agent = TradingFloor(st.session_state["project_name"], st.session_state["project_id"])

# Bind tools
all_tools = get_research_tools() + get_excel_tools() + get_ppt_tools() + get_dcf_tools() + get_social_media_tools() + get_deep_research_tools()
agent.set_tools(all_tools)

st.session_state["agent"] = agent

# Sidebar for Project Context & Files
with st.sidebar:
    st.header("Deal Context")
    
    # Fetch all known projects
    all_projects = get_all_projects()
    if not all_projects:
        all_projects = ["Project Alpha"]
        
    if st.session_state["project_name"] not in all_projects:
        all_projects.insert(0, st.session_state["project_name"])
        
    selected_project = st.selectbox("Switch Project", options=all_projects, index=all_projects.index(st.session_state["project_name"]))
    if selected_project != st.session_state["project_name"]:
        st.session_state["project_name"] = selected_project
        st.session_state["project_id"] = get_or_create_project(selected_project)
        st.session_state["agent"] = TradingFloor(selected_project, st.session_state["project_id"])
        st.session_state["agent"].set_tools(get_research_tools() + get_excel_tools() + get_ppt_tools() + get_dcf_tools() + get_social_media_tools() + get_deep_research_tools())
        st.rerun()

    with st.expander("Create New Project"):
        new_project_name = st.text_input("New Project Name")
        if st.button("Create") and new_project_name:
            st.session_state["project_name"] = new_project_name
            st.session_state["project_id"] = get_or_create_project(new_project_name)
            st.rerun()

    with st.expander("Delete Project"):
        st.warning(f"Delete '{st.session_state['project_name']}'?")
        if st.button("Confirm Delete"):
            delete_project(st.session_state["project_id"])
            if "project_name" in st.session_state: del st.session_state["project_name"]
            if "project_id" in st.session_state: del st.session_state["project_id"]
            if "agent" in st.session_state: del st.session_state["agent"]
            st.rerun()
            
    st.divider()
    
    st.subheader("Swarm Configuration")
    swarm_options = ["Banking Team (Default)", "Dynamic Personas (Auto-generated)"]
    current_mode = st.session_state["swarm_mode"]
    st.session_state["swarm_mode"] = st.radio(
        "Agent Selection",
        options=swarm_options,
        index=swarm_options.index(current_mode) if current_mode in swarm_options else 0,
        help="Choose whether to use the default Banking personas or let the LLM auto-generate personas based on the query."
    )
    
    st.divider()
    
    st.subheader("Current Assumptions")
    assumptions = get_assumptions(st.session_state["project_id"])
    if assumptions:
        for k, v in assumptions.items():
            st.markdown(f"**{k}:** {v}")
    else:
        st.info("No assumptions set yet. Ask the agent to build a model or research a target.")
        
    st.divider()
    
    st.subheader("Generated Files")
    files = get_tracked_files(st.session_state["project_id"])
    if files:
        for f in files:
            # We assume files are in an 'output' directory. For now just show name.
            st.markdown(f"📄 `{f['filename']}` ({f['file_type']})")
    else:
        st.info("No files generated yet.")
        
    st.divider()
    st.subheader("Upload Research")
    uploaded_file = st.file_uploader("Upload 10-K or Pitchbook (PDF)", type=["pdf"])
    if uploaded_file:
        st.success(f"Parsed {uploaded_file.name}")
        # To do: hook this up to parse_financial_document tool or ingest vector db

# Main Chat Interface
history = get_conversation_history(st.session_state["project_id"], limit=50)

AVATARS = {
    "user": "🧑‍💼",
    "The Bull": "🐂",
    "The Bear": "🐻",
    "The Quant": "🧮",
    "The MD": "🏦",
    "model": "🏦" # Fallback for old history
}

for msg in history:
    role = msg['role']
    avatar = AVATARS.get(role, "🤖")
    with st.chat_message(role if role != "user" else "user", avatar=avatar):
        # Add the persona name bolded for clarity 
        if role != "user":
            st.markdown(f"**{role}**\n\n{msg['content']}")
        else:
            st.markdown(msg['content'])

user_input = st.chat_input("E.g., Research Target X and propose an LBO structure...")
st.markdown("---")
st.subheader("🕸️ Swarm Intelligence Network")
graph_container = st.empty()

config = {}

if "chat_nodes" not in st.session_state:
    st.session_state["chat_nodes"] = [{"id": "user", "label": "User Task", "size": 25, "color": "#00f3ff"}]
if "chat_edges" not in st.session_state:
    st.session_state["chat_edges"] = []
    
if "graph_update_counter" not in st.session_state:
    st.session_state["graph_update_counter"] = 0

render_graph_outside = True

if user_input:
    render_graph_outside = False
    # Display user message instantly
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(user_input)
        
    st.session_state["chat_nodes"] = [{"id": "user", "label": "User Task", "size": 25, "color": "#00f3ff"}]
    st.session_state["chat_edges"] = []
        
    # Get agent responses sequentially
    with st.spinner("The swarm is analyzing..."):
        for event in st.session_state["agent"].chat(user_input, swarm_mode=st.session_state["swarm_mode"]):
            # Gracefully handle Streamlit Python module cache holding onto old tuple version
            dynamic_avatar = None
            dynamic_color = None
            if isinstance(event, tuple):
                persona = event[0]
                text = event[1]
                if persona == "The Bull": sources = ["user"]
                elif persona == "The Bear": sources = ["The Bull"]
                elif persona == "The Quant": sources = ["The Bear"]
                else: sources = ["The Bull", "The Bear", "The Quant"]
                round_idx = 1
                node_id = persona
            else:
                persona = event["agent"]
                text = event["text"]
                sources = event["sources"]
                round_idx = event.get("round", 1)
                node_id = event.get("node_id", persona)
                dynamic_avatar = event.get("avatar")
                dynamic_color = event.get("color")
            
            color = "#888888"
            if dynamic_color: color = dynamic_color
            elif "The Bull" in persona: color = "#22c55e" # Green
            elif "The Bear" in persona: color = "#ef4444" # Red
            elif "The Quant" in persona: color = "#3b82f6" # Blue
            elif "The MD" in persona: color = "#eab308" # Gold
            
            label_text = persona if round_idx == 1 else f"{persona} (R{round_idx})"
            
            # Add node
            st.session_state["chat_nodes"].append({"id": node_id, "label": label_text, "size": 35, "color": color})
            for src in sources:
                # Map 'user' back to 'User Task' for the graph
                if src == "user":
                    src = "user"
                st.session_state["chat_edges"].append({"source": src, "target": node_id})
                
            # Re-rendering the custom React component during the LLM streaming loop crashes the iframe
            # due to WebSocket overload. We must defer all graph drawing to the end of the simulation.
                
            avatar = dynamic_avatar if dynamic_avatar else AVATARS.get(persona, "🤖")
            with st.chat_message(persona, avatar=avatar):
                st.markdown(f"**{label_text}**\n\n{text}")
        
    st.rerun()

if render_graph_outside:
    with graph_container:
        with open("components/swarm_network_template.html", "r") as f:
            html_template = f.read()
        nodes_json = json.dumps(st.session_state["chat_nodes"])
        edges_json = json.dumps(st.session_state["chat_edges"])
        html_code = html_template.replace("{{NODES}}", nodes_json).replace("{{EDGES}}", edges_json)
        components.html(html_code, height=450)
