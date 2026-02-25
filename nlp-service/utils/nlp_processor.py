import nltk
from nltk.tokenize import word_tokenize
from nltk.tag import pos_tag
from nltk.chunk import ne_chunk
from typing import Dict, List, Any, Optional

class NLPProcessor:
    """
    Local NLP Processor using NLTK for linguistic analysis.
    NLTK is used here for better compatibility with Python 3.14.
    """
    
    def __init__(self):
        # Ensure necessary data is downloaded
        print("🧠 Initializing Local NLP (NLTK) Processor...")
        self.initialized = False
        packages = ['punkt', 'averaged_perceptron_tagger', 'maxent_ne_chunker', 'words', 'punkt_tab', 'averaged_perceptron_tagger_eng']
        
        missing = []
        for pkg in packages:
            try:
                # Try to find the package data in local paths
                if pkg == 'punkt':
                    nltk.data.find('tokenizers/punkt')
                elif pkg == 'punkt_tab':
                    nltk.data.find('tokenizers/punkt_tab')
                elif 'tagger' in pkg:
                    nltk.data.find(f'taggers/{pkg}')
                elif 'chunker' in pkg:
                    nltk.data.find(f'chunkers/{pkg}')
                elif pkg == 'words':
                    nltk.data.find('corpora/words')
                else:
                    nltk.data.find(pkg)
            except LookupError:
                missing.append(pkg)
        
        if not missing:
            print("✅ All NLTK packages found locally.")
            self.initialized = True
            return

        print(f"📥 Missing NLTK packages: {missing}. Attempting download...")
        try:
            for pkg in missing:
                # Use a shorter timeout if we could, but NLTK doesn't expose it easily.
                # Instead, we just try to download and catch errors.
                nltk.download(pkg, quiet=True)
            print("✅ NLTK Data verified and ready")
            self.initialized = True
        except Exception as e:
            print(f"⚠️  NLTK download failed: {e}")
            print(f"💡 Tip: If you are offline, please download the packages manually.")
            # Even if download fails, we set initialized to False so analyze_query skips NLTK work
            self.initialized = False

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Perform local NLP analysis using NLTK patterns.
        """
        if not self.initialized:
            return {"intent": "find", "entities": []}
            
        # Tokenize and Tag
        tokens = word_tokenize(query)
        tagged = pos_tag(tokens)
        
        # 1. Detect Intent based on verbs
        intent = "find" # default
        query_lower = query.lower()
        
        # Verb-based intent detection
        verbs = [word.lower() for word, tag in tagged if tag.startswith('VB')]
        
        if any(v in ["delete", "remove", "drop", "clear"] for v in verbs) or "delete" in query_lower:
            intent = "delete"
        elif any(v in ["update", "change", "set", "modify"] for v in verbs) or "update" in query_lower:
            intent = "update"
        elif any(v in ["add", "insert", "create", "new"] for v in verbs) or "insert" in query_lower:
            intent = "insert"
        elif any(v in ["group", "count", "average", "sum", "total"] for v in verbs) or "total" in query_lower:
            intent = "aggregate"

        # 2. Extract Entities using NLTK ne_chunk
        entities = []
        try:
            tree = ne_chunk(tagged)
            for chunk in tree:
                if hasattr(chunk, 'label'):
                    entities.append({
                        "text": ' '.join(c[0] for c in chunk),
                        "label": chunk.label()
                    })
        except:
            pass

        return {
            "intent": intent,
            "entities": entities,
            "tokens": tokens,
            "library": "nltk"
        }

# Global processor instance
processor = NLPProcessor()
