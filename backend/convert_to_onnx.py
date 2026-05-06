from pathlib import Path
d = Path('distilbert_classifier')
onnx = d / 'model.onnx'
safetensors = d / 'model.safetensors'
if safetensors.exists() and not onnx.exists():
    print('Converting DistilBERT to ONNX at build time...')
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer
    model = ORTModelForSequenceClassification.from_pretrained(str(d), export=True)
    tokenizer = AutoTokenizer.from_pretrained(str(d))
    model.save_pretrained(str(d))
    tokenizer.save_pretrained(str(d))
    print('ONNX conversion complete')
elif onnx.exists():
    print('ONNX model already exists, skipping')
else:
    print('No DistilBERT model found, will use TF-IDF+LR fallback')