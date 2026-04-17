from piper import PiperVoice

voice = PiperVoice.load("models/piper/en_US-lessac-medium.onnx")
voice.speak("ARGOS is ready.")
