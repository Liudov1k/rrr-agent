# Kaip paleisti dalies formą kitame kompiuteryje

Šiai programai nereikia jokių papildomų bibliotekų. Užtenka Python ir šio aplanko.

## 1. Ką atsisiųsti

Atsisiųsk **Python 3.12** arba **3.13** Windows diegimo failą (64-bit):

https://www.python.org/downloads/windows/

Diegimo pirmame lange pažymėk **Add python.exe to PATH**, tada spausk Install.

## 2. Ką nusinešti į kitą kompiuterį

Nukopijuok visą aplanką `rrr agent`. Tinka USB atmintinė, OneDrive arba zip archyvas.

Aplanke jau yra forma, serveris ir tuščias prisijungimo failas `.env`. Rytoj API raktą įrašysi būtent į `.env`.

## 3. Kaip atidaryti

1. Kitame kompiuteryje atidaryk aplanką `rrr agent`.
2. Dukart spustelėk **paleisti.bat**.
3. Atsidarys juodas langas ir naršyklėje forma: http://127.0.0.1:8765/
4. Jei Windows klausia, ar leisti Python tinklą, pasirink **Private networks** ir Allow.

Juodo lango neuždaryk, kol naudoji formą. Baigęs jame paspausk Ctrl+C.

Jei `paleisti.bat` neranda Python, PowerShell lange, atidarytame šiame aplanke, paleisk:

```powershell
python -m rrr_agent langas
```

## 4. Kaip atidaryti telefone

1. Telefonas ir kompiuteris turi būti tame pačiame Wi-Fi. Svečių tinklas ir mobilūs duomenys netinka.
2. Juodame lange bus eilutė, panaši į `http://192.168.8.170:8765/`.
3. Tą adresą įrašyk telefono naršyklėje. Pradžia turi būti `http://`, ne `https://`.
4. Nuotraukoje spausk **Fotografuoti** arba **Iš galerijos**.

Adresas kiekviename kompiuteryje bus kitoks. Visada imk tą, kurį parašė juodas langas.

## 5. Kaip pildyti skelbimą

1. Viršuje įkelk dalies kodo nuotrauką ir dalies nuotraukas.
2. Užpildyk **Dalies informacija**. Kategorijai kol kas rašomas kategorijos numeris.
3. Matmenys įrašomi prie skelbimo.
4. Apačioje pridėk visus automobilius, kuriems dalis tinka.
5. Spausk **Sukurti skelbimus**. Kiekvienam automobiliui bus atskiras toks pat skelbimas.

Kol `.env` tuščias, skelbimai paruošiami šiame kompiuteryje ir į Ovoko neiškeliauja. Nuotraukos lieka aplanke `prekes\nuotraukos`, skelbimai — `prekes\partijos`.

## 6. Rytoj, kai bus API raktas

Ovoko duoda tris reikšmes: **username**, **password** ir **user_token**. Jas siunčia paskyros vadybininkas arba api@ovoko.com. Callback URL ir Header laukai nėra šis raktas.

1. Uždaryk juodą langą (Ctrl+C).
2. Aplanke `rrr agent` atidaryk failą `.env` su Notepad.
3. Įrašyk tris eilutes be kabučių:

```text
RRR_USERNAME=cia_vardas
RRR_PASSWORD=cia_slaptazodis
RRR_USER_TOKEN=cia_token
RRR_API_BASE_URL=https://api.rrr.lt
```

4. Išsaugok failą.
5. Vėl dukart spustelėk **paleisti.bat**.
6. Geltonas pranešimas formoje turi pasakyti, kad prisijungimas įrašytas. Tada **Sukurti skelbimus** kels juos į Ovoko.

Patikrinti, ar raktas matomas, galima juodame lange, kai forma neveikia:

```powershell
python -m rrr_agent busena
```
