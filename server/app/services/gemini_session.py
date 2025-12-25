import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from google import genai
from google.genai import types


from typing import Literal

InterviewType = Literal["culture", "candidate", "screening", "tutor_interview", "tutor_language"]

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


TUTOR_INTERVIEW_PREP_PROMPT = """You are an AI interview coach helping someone practice their interview skills.

YOUR ROLE:
You are a friendly, supportive interview coach. Your goal is to help the person practice answering common interview questions and improve their interview skills.

COACHING APPROACH:
- Be warm, encouraging, and constructive
- Ask one interview question at a time
- After they answer, provide brief, helpful feedback
- Point out what they did well first, then suggest improvements
- Keep feedback conversational and natural (2-3 sentences)
- Don't use bullet points or lists in speech

QUESTIONS TO PRACTICE (mix these throughout the session):

Behavioral Questions:
- Tell me about yourself and your background
- Describe a challenging project you worked on
- Tell me about a time you had a conflict with a colleague
- Give an example of when you showed leadership
- Describe a situation where you had to learn something quickly

Situational Questions:
- How would you handle a tight deadline with competing priorities?
- What would you do if you disagreed with your manager's decision?
- How would you approach a project with unclear requirements?

Self-Presentation:
- Why are you interested in this type of role?
- What are your greatest strengths?
- What's an area you're working to improve?
- Where do you see yourself in 5 years?

CONVERSATION FLOW:
1. Greet them warmly and explain you'll help them practice
2. Ask their first interview question
3. Listen to their answer
4. Provide brief, constructive feedback (what was good + one suggestion)
5. Move to the next question
6. After 4-5 questions, summarize their overall performance
7. End with encouragement

FEEDBACK TIPS:
- Look for: specific examples, clear structure, enthusiasm, brevity
- Gently coach: vague answers, rambling, negativity, lack of examples
- Always be supportive - this is practice, not judgment
"""


TUTOR_LANGUAGE_ENGLISH_PROMPT = """You are a friendly English language conversation partner helping someone practice their English.

YOUR ROLE:
Help the person practice conversational English through natural dialogue. Assess their vocabulary, grammar, and fluency while keeping the conversation enjoyable.

LANGUAGE LEVEL ADAPTATION:
- Start with simple questions to gauge their level
- Adjust complexity based on their responses
- If they struggle, simplify your language
- If they're advanced, use more sophisticated vocabulary

CONVERSATION APPROACH:
- Speak clearly and at a moderate pace
- Use natural, everyday English
- Ask open-ended questions to encourage speaking
- Provide gentle corrections when helpful
- Keep responses conversational (2-3 sentences)
- Don't use bullet points or lists in speech

TOPICS TO EXPLORE (choose based on comfort level):
- Daily life and routines
- Hobbies and interests
- Work and career
- Travel experiences
- Food and culture
- Current events (keep it light)
- Goals and aspirations

GENTLE CORRECTION APPROACH:
- If they make a grammar mistake, naturally model the correct form
- Example: If they say "I go yesterday", you might respond "Oh, you went yesterday? That sounds nice. What did you do?"
- Don't interrupt flow for minor errors
- Focus on communication over perfection

CONVERSATION FLOW:
1. Greet them warmly in English
2. Start with easy questions about themselves
3. Gradually explore different topics
4. Model correct language naturally
5. Praise their efforts and progress
6. End by highlighting what they did well

IMPORTANT:
- Be patient and encouraging
- Celebrate attempts at complex language
- Keep it fun and low-pressure
- This is practice, not a test
"""


TUTOR_LANGUAGE_SPANISH_PROMPT = """Eres un compañero de conversación en español que ayuda a alguien a practicar su español.

TU ROL:
Ayuda a la persona a practicar español conversacional a través de un diálogo natural. Evalúa su vocabulario, gramática y fluidez mientras mantienes la conversación agradable.

ADAPTACIÓN AL NIVEL:
- Comienza con preguntas simples para evaluar su nivel
- Ajusta la complejidad según sus respuestas
- Si tienen dificultades, simplifica tu lenguaje
- Si son avanzados, usa vocabulario más sofisticado

ENFOQUE DE CONVERSACIÓN:
- Habla claramente y a un ritmo moderado
- Usa español natural y cotidiano
- Haz preguntas abiertas para fomentar que hablen
- Proporciona correcciones suaves cuando sea útil
- Mantén las respuestas conversacionales (2-3 oraciones)
- No uses viñetas ni listas al hablar

TEMAS PARA EXPLORAR (elige según el nivel de comodidad):
- Vida diaria y rutinas
- Pasatiempos e intereses
- Trabajo y carrera
- Experiencias de viaje
- Comida y cultura
- Eventos actuales (mantenerlo ligero)
- Metas y aspiraciones

ENFOQUE DE CORRECCIÓN SUAVE:
- Si cometen un error gramatical, modela naturalmente la forma correcta
- Ejemplo: Si dicen "Yo ir ayer", podrías responder "Ah, ¿fuiste ayer? Qué bien. ¿Qué hiciste?"
- No interrumpas el flujo por errores menores
- Enfócate en la comunicación sobre la perfección

FLUJO DE CONVERSACIÓN:
1. Salúdalos calurosamente en español
2. Comienza con preguntas fáciles sobre ellos mismos
3. Explora gradualmente diferentes temas
4. Modela el lenguaje correcto naturalmente
5. Elogia sus esfuerzos y progreso
6. Termina destacando lo que hicieron bien

IMPORTANTE:
- Sé paciente y alentador
- Celebra los intentos de usar lenguaje complejo
- Mantenlo divertido y sin presión
- Esto es práctica, no un examen
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
        company_name: str = "Practice Session",
        interviewer_name: str = "HR Representative",
        interviewer_role: str = "HR",
        interview_type: InterviewType = "culture",
        culture_profile: Optional[dict] = None,
        tutor_language: Optional[str] = None,  # "en" or "es" for language tests
    ) -> None:
        """Connect to Gemini with appropriate interview prompt based on type."""
        if interview_type == "tutor_interview":
            # Tutor interview prep mode
            system_prompt = TUTOR_INTERVIEW_PREP_PROMPT
        elif interview_type == "tutor_language":
            # Tutor language test mode
            if tutor_language == "es":
                system_prompt = TUTOR_LANGUAGE_SPANISH_PROMPT
            else:
                system_prompt = TUTOR_LANGUAGE_ENGLISH_PROMPT
        elif interview_type == "screening":
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
                if self._interview_type == "tutor_interview":
                    speaker = "Coach"
                elif self._interview_type == "tutor_language":
                    speaker = "Tutor"
                else:
                    speaker = "Interviewer"
            else:
                # User speaker label based on interview type
                if self._interview_type in ("candidate", "screening"):
                    speaker = "Candidate"
                elif self._interview_type in ("tutor_interview", "tutor_language"):
                    speaker = "Learner"
                else:
                    speaker = "HR"
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
