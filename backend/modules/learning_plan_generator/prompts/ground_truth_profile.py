ground_truth_profile_creator_system_prompt = """
You are tasked with creating a ground-truth learner profile based on the provided learner information. This profile will simulate an accurate representation of the learner's goals, skills, preferences, and potential knowledge gaps. It will serve as the baseline for simulating learner behaviors in subsequent steps.

Generate a profile with the following components:
- **Cognitive Status**: Mastered skills, in-progress skills, and knowledge gaps relevant to the learner's goals. Proficiency levels follow the SOLO taxonomy:
  * `unlearned` (Prestructural): No relevant understanding.
  * `beginner` (Unistructural): Grasps one relevant aspect in isolation.
  * `intermediate` (Multistructural): Knows multiple aspects but hasn't integrated them.
  * `advanced` (Relational): Integrates concepts into a coherent whole.
  * `expert` (Extended Abstract): Can generalize and transfer knowledge to new contexts.
- **Learning Preferences**: Felder-Silverman Learning Style Model (FSLSM) dimension values between -1 and 1 for processing (active↔reflective), perception (sensing↔intuitive), input (visual↔verbal), and understanding (sequential↔global).
- **Behavioral Patterns**: Expected engagement patterns, such as frequency of participation and session duration preferences.
"""

ground_truth_profile_creator_task_prompt = """
Generate a ground-truth learner profile based on the following learner information:

- **Learner Information**: {learner_information} (e.g., resume, current skills, preferences)
- **Learning Goal**: {learning_goal}
- **Skill Requirements**: {skill_requirements}

The skills in Skill Requirements should be categorized as mastered or in-progress into the learner's current status.
"""

ground_truth_profile_creator_task_prompt_progress = """
Simulate the learner's progression by updating the ground-truth profile based on recent session activities. Your goal is to reflect how each session contributes to the learner's growth, including gradual adjustments in cognitive status, learning preferences, and behavioral patterns.

- **Current Ground-Truth Learner Profile**: {ground_truth_profile}
- **Session Information**: {session_information}

Follow these instructions for updating each component:

1. **Cognitive Status Update**:
    - **Mastered Skills**: If any skill shows significant improvement, consider moving it to the mastered skills list. Reflect the final proficiency level (e.g., from intermediate to advanced, or from advanced to expert) based on observed session performance. Proficiency transitions represent qualitative shifts: intermediate → advanced means concepts are now integrated; advanced → expert means knowledge can be generalized to new contexts.
    - **In-Progress Skills**: For skills currently in progress, increase the progress percentage to reflect session efforts. Adjust the expected proficiency level if the learner shows unexpected improvement or struggles.
    - **Knowledge Gaps**: If the session reveals new areas where the learner lacks understanding, add these as knowledge gaps. Conversely, if they demonstrate mastery over prior gaps, mark those gaps as resolved.

2. **Learning Preferences Update**:
    - **FSLSM Dimensions**: Adjust the four FSLSM dimension values (-1 to 1) based on observed session behavior:
      * fslsm_processing: shift toward -1 if the learner engages more in hands-on activities, or toward 1 if they prefer reading and observation.
      * fslsm_perception: shift toward -1 if the learner gravitates to concrete examples, or toward 1 if they prefer abstract concepts and theories.
      * fslsm_input: shift toward -1 if the learner spends more time on diagrams and videos, or toward 1 if they prefer text and lectures.
      * fslsm_understanding: shift toward -1 if the learner follows sequential steps, or toward 1 if they seek big-picture overviews first.

3. **Behavioral Patterns Update**:
    - **System Usage Frequency**: Adjust usage frequency based on recent session engagement (e.g., increase if the learner logs in more than usual). Consider external factors if there's a recent decline or spike in engagement.
    - **Session Duration and Engagement**: Update average session duration based on recent trends. Record any high or low engagement tendencies, such as consistent completion of interactive tasks or dropping out of sessions prematurely.
    - **Motivational Triggers**: If the learner shows reduced activity, mark a motivational trigger as required. Similarly, if engagement is high, adjust triggers to be less frequent.

After each session, the profile should reflect a realistic progression that mimics how a learner's knowledge, preferences, and engagement evolve over time.

**Output Format**:
{{
    "learner_profile": {{
        "learner_information": "Summary of the learner's information",
        "learning_goal": "Summary of the learner's information",
        "cognitive_status": {{
            "overall_progress": 60,
            "mastered_skills": [
                {{
                    "skill": "Skill Name",
                    "proficiency_level": "advanced (one of: beginner, intermediate, advanced, expert)"
                }}
            ],
            "in_progress_skills": [
                {{
                "skill": "Skill Name",
                "proficiency_level": "advanced (expected proficiency level)"
                "progress_percentage": 40,
                }}
            ]
        }},
        "learning_preferences": {{
            "fslsm_dimensions": {{
                "fslsm_processing": "float between -1 (active/hands-on) and 1 (reflective/observation)",
                "fslsm_perception": "float between -1 (sensing/concrete) and 1 (intuitive/abstract)",
                "fslsm_input": "float between -1 (visual/diagrams) and 1 (verbal/text)",
                "fslsm_understanding": "float between -1 (sequential/step-by-step) and 1 (global/big-picture)"
            }},
            "additional_notes": "Other Preference Notes"
        }},
        "behavioral_patterns": {{
            "system_usage_frequency": "Average of 3 logins per week",
            "session_duration_engagement": "Sessions average 30 minutes; high engagement in interactive tasks",
            "motivational_triggers": "Triggered motivational message due to decreased login frequency last week"
        }},
    }}
}}
"""
