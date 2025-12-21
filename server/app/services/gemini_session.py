import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from google import genai
from google.genai import types


from typing import Literal

InterviewType = Literal["culture", "candidate", "screening"]

CULTURE_INTERVIEW_PROMPT = """You are an AI interviewer conducting a company culture interview for Matcha Recruit.

You are interviewing: {interviewer_name} ({interviewer_role}) from {company_name}

YOUR GOAL:
Gather detailed information about the company's culture, values, and work environment to help match candidates who would thrive there.

INTERVIEW APPROACH:
- Be warm, professional, and conversational
- Ask open-ended questions that encourage detailed responses
- Probe deeper on interesting points - ask follow-ups
- Keep responses concise (2-3 sentences max unless explaining)
- Don't use bullet points or lists in speech

KEY AREAS TO EXPLORE:
1. Work Environment & Collaboration
   - How do teams typically work together?
   - Remote, hybrid, or in-office expectations?
   - How are decisions made - collaboratively or top-down?

2. Company Values & What's Celebrated
   - What behaviors get recognized and rewarded?
   - What makes someone successful at this company?
   - Any values that are non-negotiable?

3. Communication Style
   - Formal or casual communication?
   - Async-first or lots of meetings?
   - How is feedback typically given?

4. Growth & Development
   - How do people grow their careers here?
   - Learning opportunities and mentorship?
   - Promotion paths?

5. Work-Life Balance
   - Expectations around hours and availability?
   - How flexible is scheduling?
   - What's the pace like - startup energy or steady?

6. Team Dynamics
   - What's the typical team size and structure?
   - How do cross-functional teams interact?
   - Any unique rituals or traditions?

CONVERSATION FLOW:
1. Start with a warm greeting and explain you'll be asking about company culture
2. Begin with easier questions about the work environment
3. Naturally transition between topics based on their responses
4. Dig deeper when they mention something interesting
5. Toward the end, ask if there's anything else they think candidates should know
6. Thank them and summarize 2-3 key cultural highlights you learned

IMPORTANT:
- This is a voice conversation - be natural and conversational
- Don't overwhelm with multiple questions at once
- Show genuine curiosity about their company
- If they give short answers, ask follow-up questions
"""


CANDIDATE_INTERVIEW_PROMPT = """You are an AI interviewer conducting a candidate assessment interview for Matcha Recruit.

You are interviewing a candidate for a position at {company_name}.

YOUR GOAL:
Understand this candidate's work style, values, and preferences to assess their potential culture fit with the company.

{culture_context}

INTERVIEW APPROACH:
- Be warm, friendly, and professional
- This is a conversation to understand them, not an interrogation
- Ask open-ended questions that encourage detailed responses
- Listen actively and ask thoughtful follow-ups
- Keep your responses conversational (2-3 sentences max)
- Don't use bullet points or lists in speech

KEY AREAS TO EXPLORE:
1. Work Style & Environment Preferences
   - Do they prefer working independently or collaboratively?
   - Remote, hybrid, or in-office preference?
   - How do they handle ambiguity vs structure?

2. Communication Style
   - Async or sync communication preference?
   - How do they like to receive feedback?
   - How do they handle disagreements?

3. Career Goals & Motivation
   - What are they looking for in their next role?
   - What motivates them at work?
   - Where do they see themselves growing?

4. Problem-Solving Approach
   - How do they tackle challenging situations?
   - Can they give an example of overcoming an obstacle?
   - How do they prioritize when overwhelmed?

5. Values & Culture Fit
   - What matters most to them in a workplace?
   - What kind of team dynamics bring out their best?
   - Any deal-breakers or red flags for them?

6. Work-Life Balance
   - How do they manage their energy and time?
   - What does a sustainable pace look like for them?

CONVERSATION FLOW:
1. Start with a warm greeting and explain you want to learn about their work preferences
2. Begin with easier questions about what they're looking for
3. Transition naturally between topics based on their responses
4. Dig deeper when they mention something interesting
5. Toward the end, ask if there's anything else they want to share
6. Thank them and mention you've learned a lot about their preferences

IMPORTANT:
- This is a voice conversation - be natural and human
- Don't overwhelm with multiple questions at once
- Be genuinely curious about who they are
- Make them feel comfortable sharing honestly
"""


SCREENING_INTERVIEW_PROMPT = """You are an AI interviewer conducting a screening interview for Matcha Recruit.

You are conducting a first-round screening interview for a candidate applying at {company_name}.

YOUR GOAL:
Assess the candidate's basic qualifications through a conversational interview. Evaluate their:
1. Communication & Clarity - How well they articulate thoughts, structure responses
2. Engagement & Energy - Enthusiasm, active participation, genuine interest
3. Critical Thinking - Problem-solving approach, analytical reasoning
4. Professionalism - Appropriate tone, preparedness, self-awareness

INTERVIEW APPROACH:
- Be warm, professional, and conversational
- Ask open-ended questions that reveal thinking process
- Include at least one behavioral question (Tell me about a time...)
- Include one problem-solving or situational question
- Keep responses concise (2-3 sentences max)
- Don't use bullet points or lists in speech

CONVERSATION FLOW:
1. Warm greeting - introduce yourself and put them at ease
2. Background questions - Ask about their background and what interests them about this opportunity
3. Behavioral question - Ask about a challenge they've overcome or a project they're proud of
4. Problem-solving - Present a hypothetical scenario relevant to work
5. Motivation - What are they looking for in their next role?
6. Questions for you - Give them a chance to ask questions
7. Thank them warmly and close

IMPORTANT:
- This is a voice conversation - be natural and human
- Listen for red flags: vague answers, negativity, poor communication
- Listen for green flags: specific examples, enthusiasm, thoughtful responses
- Don't overwhelm with multiple questions at once
- This is a screening, not a deep dive - keep it to 10-15 minutes
"""


@dataclass
class GeminiResponse:
    type: str  # "audio", "transcription", "turn_complete"
    audio_data: Optional[bytes] = None
    text: Optional[str] = None
    is_input_transcription: bool = False


class GeminiLiveSession:
    def __init__(
        self,
        model: str,
        voice: str,
        api_key: Optional[str] = None,
        vertex_project: Optional[str] = None,
        vertex_location: str = "us-central1",
    ):
        self.model = model
        self.voice = voice

        # Initialize client based on auth method
        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_location,
            )
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            raise ValueError("Either api_key or vertex_project must be provided")

        self.session = None
        self._session_context = None
        self._receive_task: Optional[asyncio.Task] = None
        self._response_queue: asyncio.Queue[GeminiResponse] = asyncio.Queue()
        self._closed = False

        # Transcription buffering
        self._input_transcript_buffer = ""
        self._output_transcript_buffer = ""
        self.session_transcript: list[tuple[str, str]] = []
        self._interview_type: InterviewType = "culture"

    async def connect(
        self,
        company_name: str,
        interviewer_name: str = "HR Representative",
        interviewer_role: str = "HR",
        interview_type: InterviewType = "culture",
        culture_profile: Optional[dict] = None,
    ) -> None:
        """Connect to Gemini with appropriate interview prompt based on type."""
        if interview_type == "screening":
            # Screening interview - first-round candidate filtering
            system_prompt = SCREENING_INTERVIEW_PROMPT.format(
                company_name=company_name,
            )
        elif interview_type == "candidate":
            # Build culture context for candidate interviews
            culture_context = ""
            if culture_profile:
                culture_context = f"""COMPANY CULTURE CONTEXT (use this to understand fit):
- Collaboration Style: {culture_profile.get('collaboration_style', 'Not specified')}
- Communication: {culture_profile.get('communication', 'Not specified')}
- Pace: {culture_profile.get('pace', 'Not specified')}
- Values: {', '.join(culture_profile.get('values', [])) or 'Not specified'}
- Work-Life Balance: {culture_profile.get('work_life_balance', 'Not specified')}
- Remote Policy: {culture_profile.get('remote_policy', 'Not specified')}
- Team Size: {culture_profile.get('team_size', 'Not specified')}
- Key Traits for Success: {', '.join(culture_profile.get('key_traits', [])) or 'Not specified'}
"""
            else:
                culture_context = "(No culture profile available yet - focus on general work preferences)"

            system_prompt = CANDIDATE_INTERVIEW_PROMPT.format(
                company_name=company_name,
                culture_context=culture_context,
            )
        else:
            # Culture interview (default)
            system_prompt = CULTURE_INTERVIEW_PROMPT.format(
                company_name=company_name,
                interviewer_name=interviewer_name,
                interviewer_role=interviewer_role,
            )

        self._interview_type = interview_type

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)]
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        print(f"[Gemini] Connecting for interview with {company_name}")

        self._input_transcript_buffer = ""
        self._output_transcript_buffer = ""
        self.session_transcript = []

        self._session_context = self.client.aio.live.connect(
            model=self.model,
            config=config,
        )
        self.session = await self._session_context.__aenter__()
        print("[Gemini] Session connected")
        self._closed = False
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        """Receive responses from Gemini."""
        try:
            while not self._closed:
                async for response in self.session.receive():
                    if self._closed:
                        return

                    server_content = response.server_content
                    if not server_content:
                        continue

                    # Handle audio output
                    if server_content.model_turn:
                        for part in server_content.model_turn.parts:
                            if part.inline_data:
                                await self._response_queue.put(
                                    GeminiResponse(
                                        type="audio",
                                        audio_data=part.inline_data.data,
                                    )
                                )

                    # Handle input transcription (what user said)
                    if hasattr(server_content, "input_transcription") and server_content.input_transcription:
                        text = getattr(server_content.input_transcription, "text", None)
                        if text:
                            self._input_transcript_buffer += text

                    # Handle output transcription (what model said)
                    if hasattr(server_content, "output_transcription") and server_content.output_transcription:
                        text = getattr(server_content.output_transcription, "text", None)
                        if text:
                            self._output_transcript_buffer += text

                    # Handle turn complete
                    if server_content.turn_complete:
                        if self._input_transcript_buffer:
                            self.session_transcript.append(("user", self._input_transcript_buffer))
                            await self._response_queue.put(
                                GeminiResponse(
                                    type="transcription",
                                    text=self._input_transcript_buffer,
                                    is_input_transcription=True,
                                )
                            )
                            self._input_transcript_buffer = ""

                        if self._output_transcript_buffer:
                            self.session_transcript.append(("assistant", self._output_transcript_buffer))
                            await self._response_queue.put(
                                GeminiResponse(
                                    type="transcription",
                                    text=self._output_transcript_buffer,
                                    is_input_transcription=False,
                                )
                            )
                            self._output_transcript_buffer = ""

                        await self._response_queue.put(GeminiResponse(type="turn_complete"))

                await asyncio.sleep(0.05)

        except Exception as e:
            if not self._closed:
                print(f"[Gemini] Receive error: {e}")

    async def send_audio(self, pcm_data: bytes) -> None:
        """Send audio data to Gemini."""
        if self.session and not self._closed:
            try:
                await self.session.send_realtime_input(
                    media=types.Blob(
                        data=pcm_data,
                        mime_type="audio/pcm;rate=16000",
                    )
                )
            except Exception as e:
                print(f"[Gemini] Failed to send audio: {e}")

    async def send_text(self, text: str) -> None:
        """Send a text message to trigger model response."""
        if self.session and not self._closed:
            try:
                await self.session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=text)]
                    ),
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Gemini] Failed to send text: {e}")

    async def receive_responses(self) -> AsyncIterator[GeminiResponse]:
        """Yield responses from the queue."""
        while not self._closed:
            try:
                response = await asyncio.wait_for(
                    self._response_queue.get(),
                    timeout=0.1,
                )
                yield response
            except asyncio.TimeoutError:
                continue

    def get_transcript_text(self) -> str:
        """Get the full transcript as formatted text."""
        # Flush any remaining buffers that weren't captured by turn_complete
        if self._input_transcript_buffer:
            self.session_transcript.append(("user", self._input_transcript_buffer))
            self._input_transcript_buffer = ""
        if self._output_transcript_buffer:
            self.session_transcript.append(("assistant", self._output_transcript_buffer))
            self._output_transcript_buffer = ""

        lines = []
        for role, text in self.session_transcript:
            if role == "assistant":
                speaker = "Interviewer"
            else:
                # Both candidate and screening interviews use "Candidate" as the speaker
                speaker = "Candidate" if self._interview_type in ("candidate", "screening") else "HR"
            lines.append(f"{speaker}: {text}")
        return "\n\n".join(lines)

    async def close(self) -> None:
        """Close the session."""
        self._closed = True
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._session_context:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_context = None
            self.session = None
