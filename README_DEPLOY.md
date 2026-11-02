# 🚀 Free 24/7 Cloud Hosting Guide (हमेशा-हमेशा के लिए फ्री)

यह बॉट बिना कंप्यूटर और बिना मैकबुक के 24 घंटे लगातार क्लाउड पर चलाने के लिए तैयार है।

---

## 1. GitHub पर अपलोड करने के तरीके

### तरीका A: अगर आप मुझे GitHub Repo / Token देते हैं
1. GitHub पर नया खाली रेपो बनाएँ: [github.com/new](https://github.com/new) (नाम: `ipa-signer-bot`)
2. रेपो का लिंक मुझे चैट में भेजें:
   `https://github.com/<आपका-यूज़रनेम>/ipa-signer-bot`
   (साथ में GitHub Settings -> Developer Settings -> Personal Access Tokens से 1 टोकन दे सकते हैं, मैं सीधे पुश कर दूंगा)।

### तरीका B: डायरेक्ट Zip फाइल से 1-क्लिक अपलोड
1. आपके प्रोजेक्ट फोल्डर में `ipa-signer-bot.zip` तैयार है।
2. [github.com/new](https://github.com/new) पर जाएँ, नाम रखें `ipa-signer-bot` और **Create repository** पर क्लिक करें।
3. वहाँ **"uploading an existing file"** पर क्लिक करें और `ipa-signer-bot.zip` को ड्रैग करके अपलोड कर दें।

---

## 2. 100% Free 24/7 हमेशा के लिए चलने वाले होस्ट्स (No Credit Card)

### 🥇 विकल्प 1: Koyeb (100% Free Eco Tier)
- **वेबसाइट:** [koyeb.com](https://www.koyeb.com/)
- **लागत:** $0 (हमेशा के लिए मुफ़्त, कोई क्रेडिट कार्ड नहीं चाहिए)
- **कैसे सेट करें:**
  1. Koyeb पर GitHub से साइन इन करें।
  2. **Create Service** -> **GitHub** चुनें और `ipa-signer-bot` रेपो सेलेक्ट करें।
  3. Builder में **Dockerfile** अपने-आप डिटेक्ट हो जाएगा।
  4. Environment Variables में जोड़ें:
     - `BOT_TOKEN` = `8682648198:AAEdBKAgP0779Pv5EgyM5MpkGAyMIWrxA1Q`
     - `ADMIN_USERNAMES` = `yqios`
  5. **Deploy** दबाएँ। बॉट हमेशा के लिए 24 घंटे ऑनलाइन रहेगा!

---

### 🥈 विकल्प 2: Hugging Face Spaces (100% Free Docker Hosting)
- **वेबसाइट:** [huggingface.co/new-space](https://huggingface.co/new-space)
- **लागत:** $0 (16GB RAM, कभी स्लीप नहीं होता, 100% फ्री)
- **कैसे सेट करें:**
  1. Space SDK में **Docker** चुनें (Blank)।
  2. Space Visibility: **Public** या **Private**।
  3. Files में जाकर प्रोजेक्ट की फाइल्स डाल दें।
  4. Settings -> **Variables and secrets** में `BOT_TOKEN` और `ADMIN_USERNAMES` जोड़ दें।
  5. बॉट तुरंत स्टार्ट हो जाएगा और कभी बंद नहीं होगा।
