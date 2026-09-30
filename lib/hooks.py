"""Hook Library — 10 kategori hook stop-scrolling.
Referensi dari @arisnurdiansah7 (100 hook Shopee Affiliate), diklasifikasi jadi
10 tipe berdasar trigger psikologis. Dipakai buat AI generate opening yang nendang."""

HOOK_CATEGORIES = {
    "larangan": {
        "name": "Larangan",
        "desc": "Reverse psychology. Kata 'jangan' bikin orang justru penasaran.",
        "trigger": "reverse psychology / curiosity",
        "examples": [
            "Jangan checkout dulu sebelum nonton ini.",
            "Jangan skip, ini penting.",
            "Jangan beli sebelum lihat ini.",
            "Jangan sampai nyesel kayak aku.",
            "Jangan tunggu rusak baru beli.",
        ],
    },
    "penyesalan": {
        "name": "Penyesalan",
        "desc": "Fear of regret. Nyentuh rasa 'telat tahu / harusnya dari dulu'.",
        "trigger": "fear of regret",
        "examples": [
            "Nyesel baru nemu sekarang.",
            "Harusnya beli dari dulu.",
            "Kok baru tahu ada barang begini?",
            "Aku telat tahu produk ini.",
            "Kalau tahu dari dulu, hemat banyak.",
        ],
    },
    "harga": {
        "name": "Harga",
        "desc": "Kaget sama harga murah / value tak terduga.",
        "trigger": "price shock / value",
        "examples": [
            "Serius cuma belasan ribu?",
            "Segini doang harganya?",
            "Nggak nyangka semurah ini.",
            "Murah bukan berarti murahan.",
            "Dengan uang segini udah dapat ini.",
        ],
    },
    "relatable": {
        "name": "Relatable",
        "desc": "'Ini gue banget'. Bikin audiens ngerasa senasib.",
        "trigger": "relatability / belonging",
        "examples": [
            "Siapa yang rumahnya masih begini?",
            "Coba jujur, di rumah kalian juga gini kan?",
            "Ternyata aku nggak sendirian.",
            "Pernah ngalamin hal ini?",
            "Aku dulu juga gitu.",
        ],
    },
    "masalah": {
        "name": "Masalah",
        "desc": "Problem-solution. Angkat masalah lalu kasih solusi simpel.",
        "trigger": "problem-solution",
        "examples": [
            "Capek kalau harus begini terus.",
            "Ternyata solusinya sesimpel ini.",
            "Nggak perlu ribet lagi.",
            "Selama ini ternyata caranya salah.",
            "Ini penyelamat banget.",
        ],
    },
    "bukti": {
        "name": "Bukti",
        "desc": "Social proof. Tunjukin hasil nyata / pengalaman sendiri.",
        "trigger": "social proof",
        "examples": [
            "Lihat hasilnya dulu.",
            "Aku udah coba sendiri.",
            "Ternyata beneran sebagus ini.",
            "Baru sekali pakai udah kelihatan bedanya.",
            "Worth it ternyata.",
        ],
    },
    "fomo": {
        "name": "FOMO",
        "desc": "Fear of missing out. Takut ketinggalan / kehabisan.",
        "trigger": "scarcity / urgency",
        "examples": [
            "Jangan sampai kehabisan.",
            "Biasanya stoknya cepet habis.",
            "Takut besok harganya naik.",
            "Ini lagi rame dicari.",
            "Mumpung masih ada.",
        ],
    },
    "cerita": {
        "name": "Cerita",
        "desc": "Storytelling. Buka dengan narasi personal yang mancing lanjut.",
        "trigger": "narrative / storytelling",
        "examples": [
            "Awalnya aku nggak percaya.",
            "Semua berubah setelah coba ini.",
            "Berawal dari iseng.",
            "Ternyata malah jadi favorit.",
            "Pengalaman ini bikin aku kaget.",
        ],
    },
    "penasaran": {
        "name": "Penasaran",
        "desc": "Curiosity gap. Kasih teka-teki, tahan informasi.",
        "trigger": "curiosity gap",
        "examples": [
            "Ada yang aneh dari produk ini.",
            "Coba tebak harganya.",
            "Kenapa banyak yang beli ya?",
            "Ada satu hal yang bikin aku suka.",
            "Bagian ini yang paling bikin kaget.",
        ],
    },
    "cta_awal": {
        "name": "CTA di Awal",
        "desc": "Ajakan langsung di detik pertama. Perintah ringan.",
        "trigger": "direct call-to-action",
        "examples": [
            "Simpan video ini dulu.",
            "Stop scroll sebentar.",
            "Wajib lihat sampai habis.",
            "Kasih aku 15 detik, habis itu terserah kamu.",
            "Yang lagi cari barang begini, merapat.",
        ],
    },
}


def list_hooks():
    """Return list kategori + contoh buat UI."""
    return [
        {"id": k, "name": v["name"], "desc": v["desc"],
         "trigger": v["trigger"], "examples": v["examples"],
         "count": len(v["examples"])}
        for k, v in HOOK_CATEGORIES.items()
    ]


def hook_prompt(category_id, topic, lang="id"):
    """Bikin prompt buat AI generate hook baru sesuai kategori + topik."""
    cat = HOOK_CATEGORIES.get(category_id)
    if not cat:
        return None
    examples = "\n".join(f"- {e}" for e in cat["examples"])
    lang_txt = "Bahasa Indonesia santai" if lang == "id" else "casual English"
    return (
        f"Kamu ahli bikin hook stop-scrolling buat konten sosmed (Threads/Reels).\n"
        f"Tipe hook: {cat['name']} ({cat['trigger']}). {cat['desc']}\n\n"
        f"Contoh hook tipe ini:\n{examples}\n\n"
        f"Topik/produk: {topic}\n\n"
        f"Bikin 8 hook BARU tipe {cat['name']} buat topik di atas, dalam {lang_txt}.\n"
        f"Aturan: tiap hook 1 baris, pendek (max 12 kata), nendang di 3 detik pertama, "
        f"nggak pakai em-dash, nggak generik. Nomorin 1-8. Cuma hook, tanpa penjelasan."
    )
