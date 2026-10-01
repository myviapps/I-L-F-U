# Model and dataset licenses

Licenses below are from memory and must be verified against each model or dataset page before we bundle, redistribute or train on anything. Update this file in the same pull request that adds or changes a model or dataset.

| Item | Used for | License (to verify) | Redistribute with our app? | Verified on |
| --- | --- | --- | --- | --- |
| OpenAI Whisper | Speech-to-text | MIT | Yes | not yet |
| faster-whisper | Runs Whisper (CTranslate2) | MIT | Yes | not yet |
| whisper.cpp | Runs Whisper on CPU and Apple Silicon | MIT | Yes | not yet |
| pyannote.audio and its models | Speaker labels | Code MIT; some model weights gated on Hugging Face | Check before bundling | not yet |
| Common Voice | Training and evaluation data | CC0 | n/a | not yet |
| LibriSpeech | Training and evaluation data | CC-BY-4.0 | n/a | not yet |
| AMI meeting corpus | Evaluation data | CC-BY-4.0 | n/a | not yet |
| TED-LIUM | Do not use (non-commercial terms) | CC-BY-NC-ND | No | not yet |

## License of this project's own code

AGPL-3.0. Models and weights bundled or downloaded by the app keep their own licenses; fine-tuned weights we publish use the most permissive license their base model and training data allow, stated in each model card.
