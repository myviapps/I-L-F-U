# Languages

I-L-F-U uses OpenAI Whisper models, which understand about 100 languages. The setup window and the main window list the most common ones, including Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi and Urdu.

## How good is it?

Accuracy depends heavily on the language and the model size. Roughly:

- **English and other widely recorded languages** (Spanish, French, German, Portuguese): good with every model.
- **Hindi:** usable with Accurate or Best; the small models make many mistakes.
- **Telugu, Tamil, Kannada, Malayalam and other regional languages:** Whisper had far less training data for these. Expect noticeably more errors than in English, even with the Best model. Treat the output as a draft and check names, numbers and important sentences.
- **Mixed speech** (for example Hindi and English in one sentence): works partly. Choosing one language forces everything into that language; "Detect automatically" can switch between short chunks and sometimes guesses wrong.

## Measured so far

On 25 FLEURS clips per language (see `docs/BENCHMARKS.md`): English 6 to 9% word errors, Hindi 106% with the Fast model and 55% with Balanced, Telugu 134% with Fast and 118% with Balanced. With Best (large-v3-turbo, 10 clips): English 6%, Hindi 35%, Telugu 81%. In plain terms: **Hindi and Telugu are not usable with the Fast and Balanced models**; Hindi is a readable draft only with Best; **Telugu is still mostly wrong even with Best**. Medium (Accurate) scored Hindi 39% and Telugu 101%, so it is not better than Best and is much slower. Improving regional languages by fine-tuning is planned for a later phase.

## Tips

- Pick the language you hear most instead of "Detect automatically".
- Use Accurate or Best for non-English calls if your computer can run them.
- After the call, **Re-transcribe** gives a better result than the live captions.
- Good microphones and quiet rooms help more than anything else.
