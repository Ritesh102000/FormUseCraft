<!--
Formcraft by catapultaiwork — https://catapultaiwork.com
Source-available with required attribution; see LICENSE.
Personal and commercial use is allowed. Every hosted form must retain the small
"Powered by catapultaiwork" link. There is no builder setting to hide it.
People controlling the source can edit it, but the license requires this credit.
This is a custom attribution license, not standard MIT or OSI-approved open source.
-->

# AI form builder and optional voice assistance

FormUseCraft uses the installation owner's OpenAI API access. AI is optional:
manual form building, typing, Google Sheets, and meeting scheduling continue to
work without it. Respondents never enter or receive the owner's API key.

## Build a form in the dashboard

1. Sign in and choose **Build with AI**.
2. Describe the form. Optionally attach one PDF, PNG, JPEG, or WebP up to **2 MB**.
   For large PDFs, provide only the pages containing the relevant questions.
3. Enter your OpenAI API key, or use the environment key configured below.
   A key entered on this page is used only for that request, cleared from the
   input after sending, and never saved in browser storage or the database.
   Enter it again for another generation if there is no environment key.
4. Choose **Generate draft**. Review the questions and any limitations shown.
   Enter another instruction and choose **Refine draft** to revise that preview.
5. Choose **Create draft and edit**. The draft is saved to your dashboard and
   opens in the regular builder. Edit its fields and explicitly publish when ready.

Generating does not save or publish a form. Generated drafts use the existing
question types and validation, have fresh question IDs, and start with voice off.
The builder supports up to 100 generated questions. Reference uploads are inputs
to the owner tool, not a new respondent file-upload question type.

For a meeting intake, select **Add Google meeting scheduling** before creating
the draft. Connect Sheets + Calendar first. The server adds the required attendee
bindings and hidden booking metadata. Review **Meeting settings** before publishing:
the initial schedule is UTC, Monday–Friday, starts 09:00–16:30, 30-minute duration,
two hours' notice, and a 30-day booking window. The AI does not configure a Google
account or book an event. See [Google setup](GOOGLE_SHEETS.md).

Payments, conditional logic, and respondent file uploads are not implemented.
The AI should explain unsupported requirements in its notes. Always review its
output; a request for a feature does not implement that feature.

## Configure OpenAI on your deployment

Add server-side Production variables in Vercel, then redeploy. For local use,
place them in your ignored `.env`. Never commit a real key.

| Variable | Purpose / default |
| --- | --- |
| `OPENAI_API_KEY` | Your OpenAI project API key. Enables owner generation and makes per-form voice available automatically. |
| `FORMCRAFT_OPENAI_API_KEY` | Optional explicit override, taking precedence over `OPENAI_API_KEY`. |
| `FORMCRAFT_AI_MODEL` | Responses model supporting text/image/PDF input and Structured Outputs; default `gpt-4.1-mini`. |
| `FORMCRAFT_AI_TRANSCRIBE_MODEL` | Audio transcription model; default `gpt-4o-mini-transcribe`. |
| `FORMCRAFT_AI_VOICE_DAILY_TURNS` | Shared installation cap on recorded voice turns; default `200`, configurable from `0` to `5000`. `0` disables voice. |
| `FORMCRAFT_SECRET_KEY` | Existing unique installation secret, at least 32 characters for signed voice sessions. |

Use a model available to your OpenAI project and set appropriate project usage
alerts/budgets. API usage has separate costs from software and Vercel hosting.
A ChatGPT subscription is not an API key. A key entered into the owner builder
never enables public voice; public voice requires an environment key.

## Enable voice on a form

An environment OpenAI key makes voice available automatically. Open a form's
builder, turn on **AI voice assistance**, and save. Voice appears only on published
forms with this setting enabled. Draft previews do not start public voice.

No separate global enable flag is needed; the former `FORMCRAFT_AI_VOICE_ENABLED`
variable is ignored. Key access, billing, and model availability are checked when
a request reaches OpenAI, not by a paid probe on every page load. If the key is
invalid or unavailable, the visitor sees an error and can continue typing.

Visitors see a small animated globe at the bottom of the form with an invitation.
Opening it does not request microphone access. **Yes, use voice** gives consent
and starts the guided flow:

1. The assistant reads the next unanswered visible question, its help, and choices
   using browser speech synthesis. It follows the order of the form's fields.
2. It records a short answer, ending after a pause or at 30 seconds. The visitor
   can also press **Finish recording**. Audio is limited to 1 MB per request.
3. OpenAI transcribes the recording and maps it to the current field. The server
   checks options, required values, numeric bounds, and date/time formats.
4. The visitor hears and sees the proposed answer, then says **yes** or presses
   **Use this answer**. Only then is the field filled. **Try again**, **skip**, and
   **stop** are supported; manual input remains available throughout.
5. After the questions, the visitor reviews and submits the form themselves.
   On the scheduling screen, the assistant asks them to pick and confirm a time
   using the scheduler. It never selects or books that time.

The microphone stops on close, stop, page hiding, navigation, and form submission.
Existing manual answers are skipped; if a field changes during voice confirmation,
the assistant preserves the manual edit. Unclear answers and provider failures
pause automatic recording so the visitor can retry or type. Use **Skip / fill
manually** for a required field that needs typing; normal submission validation
still requires that answer.

Voice requires HTTPS (localhost is permitted by supporting browsers), microphone
permission, and browser recording support. Browser speech availability and silence
detection vary; the visible question and record button remain available. No audio
is recorded before the visitor starts. This is guided speech interaction with a
recording per turn, not a persistent Realtime call.

## What the voice assistant cannot do

Its only write surface is the current visible answer field in the browser. It
has no submit, booking, payment, email, or arbitrary execution tool. Hidden provider
metadata and payment/scheduling control fields are excluded server-side. Question
labels or speech saying “book this” cannot grant those actions.

There is no payment flow in this version. A future payment UI must perform its own
verified payment process. The browser handoff event supports a `payment` stage
that tells the visitor to pay manually; it does not implement checkout or mark a
response as paid.

## Privacy, limits, and recovery

Owner generation sends the description, optional reference, and previous draft
to OpenAI. Voice sends a short recording, its transcript, and the current field's
context. The app does not persist recordings or transcripts; confirmed field
values remain on the page until normal submission. The Responses API uses
`store: false`. This does not override [OpenAI's API data policies](https://developers.openai.com/api/docs/guides/your-data).
Browser speech synthesis uses the browser's available voice service.

The form's privacy copy discloses voice processing before consent. An installation
owner should explain their own handling of collected responses. Required provider
attribution remains visible on public forms and confirmation/booking screens.

PostgreSQL counters apply across serverless instances:

- Owner generation: 20 requests per hour.
- Voice: configured daily turn cap, plus at most 100 turns per hour and 120 turns
  per voice session. An answer and its spoken confirmation are two turns.
- Session creation: at most twice the configured daily turn cap per day.

These are fixed windows from first use, not midnight resets or dollar spending
caps. Each voice turn can make one transcription and one Responses request.
Failed provider calls consume a turn; retries are explicit. Public users share
these limits, so abuse can temporarily exhaust voice availability. Limits do not
prevent manual submissions. Use provider usage controls alongside app caps.

Sessions expire after 30 minutes and are bound to the form and its current
revision. Save a form edit, turn voice off, or unpublish it to stop new voice
requests for the previous configuration. A request already sent to OpenAI may
still finish and incur usage. Restart voice after an expired session.

| Issue | Recovery |
| --- | --- |
| No globe | Check environment key, secret length, nonzero cap, published state, and the form's voice setting. Redeploy after environment changes. |
| Owner generation fails | Check API billing/model access, enter the request key again if needed, reduce document size, or simplify the description. |
| Voice 403 | Open the canonical `FORMCRAFT_BASE_URL`; restart an expired session or one invalidated by form edits. |
| Voice 429 | Shared usage cap reached. Type answers or wait for the window to expire. |
| Microphone denied / speech unavailable | Enable browser microphone access, use the record button if speech playback fails, or fill manually. |
| Incorrect answer | Say try again, skip and type, or edit the confirmed field before submitting. |
| Meeting draft cannot be created | Connect the owner's Sheets + Calendar capability and retry. |

## Verification

Automated tests use mocked OpenAI/Google and disposable PostgreSQL. They cover
authorization, origin checks, uploads, private draft persistence, meeting field
bindings, voice opt-ins, session isolation, hidden fields, typed answers, refusals,
and concurrent usage limits. Browser smoke checks use synthetic microphone/model
responses. Live speech accuracy, model availability, billing, and Google events
must be tested with the installation owner's accounts; mocks do not verify them.

Implementation references: [OpenAI file inputs](https://developers.openai.com/api/docs/guides/file-inputs),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
and [audio transcription](https://developers.openai.com/api/docs/guides/speech-to-text).
