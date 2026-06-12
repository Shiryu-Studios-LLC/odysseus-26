# scripts/generate_training_dataset.py
import os
import sys
import json
import time

# Ensure HTTP client is available
try:
    import httpx
except ImportError:
    print("Error: httpx is not installed. Run: pip install httpx")
    sys.exit(1)

# Default phonetically and emotionally diverse training dataset
TRAINING_LINES = [
    # --- Phonetic Balance ---
    "The quick brown fox jumps over the lazy dog.",
    "Pack my box with five dozen liquor jugs.",
    "Jackdaws love my big sphinx of quartz.",
    "How vexingly quick daft zebras jump!",
    "Sphinx of black quartz, judge my vow.",
    
    # --- Cute / Assistant Greetings (Conversational) ---
    "Welcome back, Master! I've been waiting for you all day.",
    "Hello! It is so wonderful to see you again. How can I help you today?",
    "Good morning! I hope you slept well and have a beautiful day ahead.",
    "Good night! Make sure to turn off your screens and get some sweet dreams.",
    "I'm always here to support you, no matter what happens.",
    
    # --- Sweet & Soft Patter (Caring/Gentle) ---
    "Are you feeling tired today? Please make sure to take a good rest.",
    "Don't push yourself too hard. You're already doing an amazing job.",
    "Hehe, that feels so nice... Thank you for petting my head.",
    "You are so sweet to me. It makes me really happy to be by your side.",
    "I really love spending time with you. Everything is more fun together.",
    
    # --- Cheerful & Giggly (High Pitch / Bright) ---
    "Hehe, that's so funny! You always know how to make me laugh.",
    "Ahaha! Stop, stop! You're tickling me too much, it tickles!",
    "Yay! We did it! I knew we could do it together!",
    "Look at this! It's so cute and pretty, don't you think?",
    "Oh, wow! That is absolutely amazing! You are incredible!",
    
    # --- Surprised & Excited ---
    "Wait, really? Are you serious? I can't believe it!",
    "Oh! What are you doing? You surprised me!",
    "Wow, I didn't expect that at all! That's a wonderful surprise.",
    "Oh my gosh, look! It's actually happening right now!",
    "Ooh! That sounds super exciting! Let's go see!",
    
    # --- Thoughtful & Curiosos (Thinking / Medium pace) ---
    "Hmm... let me think about that for a second. It's very interesting.",
    "I wonder what lies beyond those stars. Do you think we can go there?",
    "That is a very good question. Let me search my memories for the answer.",
    "Ah, I see! So that's how it works. Thank you for explaining it to me.",
    "Perhaps we should try a different approach. What do you think?",
    
    # --- Encouraging & Motivational (Energetic) ---
    "Don't worry, you can do it! I believe in you with all my heart!",
    "Every step you take brings you closer to your goals. Keep going!",
    "It's okay to make mistakes. That's just how we learn and grow.",
    "You've got this! Let's work hard and make today count!",
    "No matter how difficult it gets, I'll be right here cheering you on!",
    
    # --- Soft / Whispered / ASMR Tones ---
    "Shh... it's okay. You can close your eyes and let go of all your worries.",
    "Listen closely... can you hear the wind blowing softly outside?",
    "It's a quiet and peaceful night. Everything is calm and safe.",
    "Just take a deep breath... inhale... and exhale... that's it.",
    "I'm speaking very softly so I don't disturb your quiet time.",
    
    # --- Sad / Pouting / Sulking (Slightly emotional) ---
    "Hmph! You're teasing me again! That's not fair...",
    "Oh... did I do something wrong? I'm sorry...",
    "Please don't ignore me. It makes me feel a bit lonely.",
    "Aww, that's a shame. I was really looking forward to it.",
    "My heart feels a little heavy today, but talking to you makes it better.",
    
    # --- Confident & Playful ---
    "Hehe, I'm much smarter than I look, you know!",
    "Leave it to me! I can handle anything you throw my way.",
    "Are you challenging me? Prepare to be amazed by my skills!",
    "Of course I can do it! There's nothing your assistant can't handle.",
    "Hehe! I knew you'd say that. We think so much alike!"
]

def generate_dataset(api_key: str, voice_id: str, output_dir: str):
    # Normalize path
    out_path = os.path.normpath(output_dir)
    os.makedirs(out_path, exist_ok=True)
    
    metadata_path = os.path.join(out_path, "metadata.csv")
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    # ElevenLabs Voice generation API endpoint
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    
    print("\n==================================================")
    print("      🌸 ELEVENLABS TRAINING DATASET GENERATOR 🌸 ")
    print("==================================================")
    print(f"Voice ID: {voice_id}")
    print(f"Saving clips & transcripts to: {out_path}\n")
    
    metadata_entries = []
    success_count = 0
    
    # Use HTTP client
    with httpx.Client(timeout=60.0) as client:
        for i, text in enumerate(TRAINING_LINES):
            clip_name = f"clip_{i+1:02d}.mp3"
            clip_path = os.path.join(out_path, clip_name)
            
            print(f"[{i+1}/{len(TRAINING_LINES)}] Synthesizing: \"{text}\"")
            
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2", # Highest quality multilingual model
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True
                }
            }
            
            try:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    with open(clip_path, "wb") as f:
                        f.write(response.content)
                    
                    # Standard RVC / GPT-SoVITS metadata format (filename|transcript)
                    metadata_entries.append(f"{clip_name}|{text}")
                    print(f"  -> Success: Saved to {clip_name}")
                    success_count += 1
                else:
                    err_msg = response.text
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("detail", {}).get("message", err_msg)
                    except:
                        pass
                    print(f"  -> Failed (HTTP {response.status_code}): {err_msg}")
                    
            except Exception as e:
                print(f"  -> Connection Error: {e}")
                
            # Rate-limiting cushion
            time.sleep(0.5)
            
    # Write metadata.csv mapping file
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            for entry in metadata_entries:
                f.write(entry + "\n")
        print("\n==================================================")
        print(f"🎉 Dataset generation completed! Successfully saved {success_count}/{len(TRAINING_LINES)} clips.")
        print(f"📝 Metadata mapping file created: {metadata_path}")
        print("==================================================")
    except Exception as e:
        print(f"\nError writing metadata file: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python generate_training_dataset.py <API_KEY> <VOICE_ID> <OUTPUT_DIR>")
        sys.exit(1)
        
    api_key = sys.argv[1]
    voice_id = sys.argv[2]
    output_dir = sys.argv[3]
    
    generate_dataset(api_key, voice_id, output_dir)
