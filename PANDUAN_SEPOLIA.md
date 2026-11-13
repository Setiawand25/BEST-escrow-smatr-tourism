# Panduan Uji BEST di Ethereum Sepolia (uji nyata)

Waktu: ±1 jam (sebagian besar menunggu blok dan finality). Biaya: ETH Sepolia gratis dari faucet. Sisa ETH dikembalikan otomatis ke dompet Anda.

## 0. Persiapan (sekali saja)
1. Pasang **Node.js 20 LTS** dari https://nodejs.org (Windows/Mac). Cek di terminal: `node -v`.
2. Di MetaMask, **buat akun baru khusus uji** (Add account). Jangan memakai akun yang menyimpan aset nyata.
3. Ambil **±0,1 ETH Sepolia** dari faucet untuk akun uji itu, misalnya Google Cloud Web3 Faucet (Ethereum Sepolia) atau faucet Alchemy/Infura. Bila perlu, ulangi esok hari.
4. Buat **RPC gratis**: daftar di alchemy.com → Create App → pilih Ethereum, jaringan **Sepolia** → salin HTTPS URL (`https://eth-sepolia.g.alchemy.com/v2/...`).
5. (Untuk verifikasi source code) buat **API key Etherscan** gratis di etherscan.io → API Keys.
6. Ekspor **private key akun uji**: MetaMask → ⋮ → Account details → Show private key.
   **Jangan pernah membagikan private key ini kepada siapa pun, termasuk ke Claude.**

## 1. Siapkan proyek
Ekstrak `smart_tourism_escrow_code.zip`, buka terminal di folder hasil ekstrak, lalu:
```
npm install
npx hardhat compile
```

## 2. Atur variabel lingkungan
**Windows (PowerShell):**
```
$env:SEPOLIA_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/API_KEY_ANDA"
$env:SEPOLIA_PRIVATE_KEY="0xPRIVATE_KEY_AKUN_UJI"
$env:ETHERSCAN_API_KEY="API_KEY_ETHERSCAN"
$env:N_BOOKINGS="20"; $env:GUESTS="5"; $env:LABEL="sepolia_run1"; $env:LEAD_S="600"; $env:STAY_S="120"
```
**Mac / Linux:**
```
export SEPOLIA_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/API_KEY_ANDA"
export SEPOLIA_PRIVATE_KEY="0xPRIVATE_KEY_AKUN_UJI"
export ETHERSCAN_API_KEY="API_KEY_ETHERSCAN"
export N_BOOKINGS=20 GUESTS=5 LABEL=sepolia_run1 LEAD_S=600 STAY_S=120
```
(LEAD_S = jarak ke check-in, dalam detik; dibuat 10 menit agar pembatalan sempat terjadi sebelum check-in.)

## 3. Jalankan kampanye uji
```
npx hardhat run scripts/sepolia_campaign.js --network sepolia
```
Skrip ini otomatis:
- men-deploy MockStablecoin dan BookingEscrow ke Sepolia;
- membuat 5 dompet tamu dan 4 alamat peran (platform, affiliate, SDG fund, hotel), lalu mengisi dompet tamu dengan ETH;
- menjalankan 20 booking secara bersamaan (create → confirm → cancel/refund ±15% → complete setelah check-out);
- mengukur latensi inklusi dan finality (±15–20 menit);
- mengembalikan sisa ETH dari dompet tamu ke akun Anda.

Hasil di folder `results/`:
- `sepolia_run1_summary.json`: ringkasan (tingkat keberhasilan, latensi median/p95, finality, gas per fungsi, tautan Etherscan);
- `sepolia_run1_tx.csv`: satu baris per transaksi (hash, blok, latensi, gas);
- `sepolia_run1_ephemeral_wallets.json`: **berisi private key dompet uji. Jangan dibagikan.**

## 4. Verifikasi source code di Etherscan (disarankan)
Ambil alamat dari `summary.json` (bagian `deploy`) dan alamat peran dari `ephemeral_wallets.json` (bagian `roles`):
```
npx hardhat verify --network sepolia ALAMAT_TOKEN
npx hardhat verify --network sepolia ALAMAT_ESCROW ALAMAT_TOKEN ALAMAT_PLATFORM ALAMAT_AFFILIATE ALAMAT_SDG 500 300 200 0
```
Setelah itu halaman kontrak di Etherscan menampilkan centang hijau "Contract Source Code Verified".

## 5. Ambil screenshot untuk artikel
Buka tautan `explorer.escrow` di `summary.json`, lalu screenshot:
1. halaman kontrak BookingEscrow (tab *Transactions*, terlihat banyak transaksi createBooking/confirmPayment/completeStay);
2. satu transaksi `completeStay` (bagian *ERC-20 Tokens Transferred* memperlihatkan pembagian ke hotel, platform, affiliate, dan SDG fund);
3. tab *Contract* dengan tanda "Verified".

## 6. Kirim ke Claude
Kirim `sepolia_run1_summary.json`, `sepolia_run1_tx.csv`, dan screenshot-nya. **Jangan kirim private key atau file ephemeral_wallets.json.** Angka nyata itu kemudian dimasukkan ke Bagian 5.3, Tabel 8, Bagian 8.4 (validasi simulasi), dan Data Availability.

## Jika ada error
- `Saldo ETH Sepolia kurang`: isi lagi dari faucet atau turunkan `FUND_ETH` (default 0.01) / `GUESTS`.
- `insufficient funds` pada tamu: naikkan `FUND_ETH` ke 0.02.
- `TooLate` pada cancel: naikkan `LEAD_S`.
- Koneksi putus atau timeout: jalankan ulang; kontrak lama bisa dipakai kembali dengan `ESCROW=0x... TOKEN=0x...`.
