
const TMC_REGISTER_DOMAIN = new TextEncoder().encode(
    "TMC-REGISTER-V1\u0000"
);

const TMC_PBKDF2_ITERATIONS = 600000;


// Baýtlary HEX görnüşine öwürmek.
function toHex(bytes) {
    return Array.from(bytes)
        .map(byte => byte.toString(16).padStart(2, "0"))
        .join("");
}


// Baýtlary Base64 görnüşine öwürmek.
function toBase64(bytes) {
    let binary = "";

    for (const byte of bytes) {
        binary += String.fromCharCode(byte);
    }

    return btoa(binary);
}


// TMC salgysyny döretmek.
async function createTMCAddress(publicKeyBytes) {
    const hash = await crypto.subtle.digest(
        "SHA-256",
        publicKeyBytes
    );

    return "tmc_" + toHex(new Uint8Array(hash)).slice(0, 40);
}


// Python canonical_json() bilen gabat gelýän JSON.
function canonicalJSON(data) {
    const sorted = {};

    Object.keys(data)
        .sort()
        .forEach(key => {
            sorted[key] = data[key];
        });

    return JSON.stringify(sorted);
}


// Tranzaksiýa gol çekmek üçin maglumatlary taýýarlamak.
function registrationSigningBytes(transaction) {
    const jsonBytes = new TextEncoder().encode(
        canonicalJSON(transaction)
    );

    const result = new Uint8Array(
        TMC_REGISTER_DOMAIN.length + jsonBytes.length
    );

    result.set(TMC_REGISTER_DOMAIN, 0);
    result.set(jsonBytes, TMC_REGISTER_DOMAIN.length);

    return result;
}


// Hususy açary parol bilen şifrlemek.
async function encryptPrivateKey(privateKeyBytes, password) {
    if (password.length < 12) {
        throw new Error(
            "Wallet password must contain at least 12 characters."
        );
    }

    const salt = crypto.getRandomValues(
        new Uint8Array(16)
    );

    const iv = crypto.getRandomValues(
        new Uint8Array(12)
    );

    const passwordKey = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(password),
        "PBKDF2",
        false,
        ["deriveKey"]
    );

    const encryptionKey = await crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt: salt,
            iterations: TMC_PBKDF2_ITERATIONS,
            hash: "SHA-256",
        },
        passwordKey,
        {
            name: "AES-GCM",
            length: 256,
        },
        false,
        ["encrypt"]
    );

    const encrypted = await crypto.subtle.encrypt(
        {
            name: "AES-GCM",
            iv: iv,
        },
        encryptionKey,
        privateKeyBytes
    );

    return {
        version: 1,
        algorithm: "Ed25519",
        encryption: "AES-256-GCM",
        kdf: "PBKDF2-SHA256",
        iterations: TMC_PBKDF2_ITERATIONS,
        salt: toBase64(salt),
        iv: toBase64(iv),
        ciphertext: toBase64(
            new Uint8Array(encrypted)
        ),
    };
}


// Şifrlenen gapjygy IndexedDB-de saklamak.
function saveEncryptedWallet(wallet) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open("TMCWalletDB", 1);

        request.onupgradeneeded = () => {
            const db = request.result;

            if (!db.objectStoreNames.contains("wallets")) {
                db.createObjectStore("wallets", {
                    keyPath: "address",
                });
            }
        };

        request.onerror = () => reject(request.error);

        request.onsuccess = () => {
            const db = request.result;

            const transaction = db.transaction(
                "wallets",
                "readwrite"
            );

            transaction.objectStore("wallets").put(wallet);

            transaction.oncomplete = () => {
                db.close();
                resolve();
            };

            transaction.onerror = () => {
                db.close();
                reject(transaction.error);
            };
        };
    });
}


// Täze TMC gapjygyny döretmek we hasaba alyş tranzaksiýasyna gol çekmek.
async function createTMCWallet(password) {
    const keyPair = await crypto.subtle.generateKey(
        {
            name: "Ed25519",
        },
        true,
        ["sign", "verify"]
    );

    const publicKeyBytes = new Uint8Array(
        await crypto.subtle.exportKey(
            "raw",
            keyPair.publicKey
        )
    );

    const privateKeyBytes = new Uint8Array(
        await crypto.subtle.exportKey(
            "pkcs8",
            keyPair.privateKey
        )
    );

    const publicKeyHex = toHex(publicKeyBytes);

    const address = await createTMCAddress(
        publicKeyBytes
    );

    const transactionFields = {
        type: "register_account",
        address: address,
        public_key: publicKeyHex,
    };

    const signingBytes = registrationSigningBytes(
        transactionFields
    );

    const signature = await crypto.subtle.sign(
        {
            name: "Ed25519",
        },
        keyPair.privateKey,
        signingBytes
    );

    const transactionData = {
        ...transactionFields,
        signature: toHex(new Uint8Array(signature)),
    };

    const encryptedKey = await encryptPrivateKey(
        privateKeyBytes,
        password
    );

    const walletBackup = {
        address: address,
        public_key: publicKeyHex,
        ...encryptedKey,
    };

    await saveEncryptedWallet(walletBackup);

    return {
        address: address,
        public_key: publicKeyHex,
        transaction: transactionData,
    };
}


async function testTMCWalletCompatibility() {
    const keyPair = await crypto.subtle.generateKey(
        { name: "Ed25519" },
        true,
        ["sign", "verify"]
    );

    const publicKey = new Uint8Array(
        await crypto.subtle.exportKey("raw", keyPair.publicKey)
    );

    const address = await createTMCAddress(publicKey);

    const fields = {
        type: "register_account",
        address: address,
        public_key: toHex(publicKey),
    };

    const signature = await crypto.subtle.sign(
        { name: "Ed25519" },
        keyPair.privateKey,
        registrationSigningBytes(fields)
    );

    const transaction = {
        ...fields,
        signature: toHex(new Uint8Array(signature)),
    };

    console.log("TMC compatibility test:");
    console.log(JSON.stringify(transaction, null, 2));

    return transaction;
}


// Base64 maglumatyny byte görnüşine öwürmek.
function fromBase64(value) {
    const binary = atob(value);

    return Uint8Array.from(
        binary,
        character => character.charCodeAt(0)
    );
}


// IndexedDB-den öň döredilen gapjygy almak.
function getEncryptedWallet(address) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open("TMCWalletDB", 1);

        request.onerror = () => reject(request.error);

        request.onsuccess = () => {
            const db = request.result;

            if (!db.objectStoreNames.contains("wallets")) {
                db.close();
                resolve(null);
                return;
            }

            const transaction = db.transaction(
                "wallets",
                "readonly"
            );

            const getRequest = transaction
                .objectStore("wallets")
                .get(address);

            getRequest.onsuccess = () => {
                const wallet = getRequest.result || null;
                db.close();
                resolve(wallet);
            };

            getRequest.onerror = () => {
                db.close();
                reject(getRequest.error);
            };
        };
    });
}


// Şifrlenen hususy açary açmak.
async function decryptPrivateKey(wallet, password) {
    if (
        wallet.version !== 1 ||
        wallet.algorithm !== "Ed25519" ||
        wallet.encryption !== "AES-256-GCM" ||
        wallet.kdf !== "PBKDF2-SHA256" ||
        wallet.iterations !== TMC_PBKDF2_ITERATIONS
    ) {
        throw new Error("Unsupported wallet backup format.");
    }

    const salt = fromBase64(wallet.salt);
    const iv = fromBase64(wallet.iv);
    const ciphertext = fromBase64(wallet.ciphertext);

    if (salt.length !== 16 || iv.length !== 12) {
        throw new Error("Invalid wallet encryption parameters.");
    }

    const passwordKey = await crypto.subtle.importKey(
        "raw",
        new TextEncoder().encode(password),
        "PBKDF2",
        false,
        ["deriveKey"]
    );

    const encryptionKey = await crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt: salt,
            iterations: wallet.iterations,
            hash: "SHA-256",
        },
        passwordKey,
        {
            name: "AES-GCM",
            length: 256,
        },
        false,
        ["decrypt"]
    );

    try {
        return new Uint8Array(
            await crypto.subtle.decrypt(
                {
                    name: "AES-GCM",
                    iv: iv,
                },
                encryptionKey,
                ciphertext
            )
        );
    } catch {
        throw new Error("Incorrect wallet password or corrupted backup.");
    }
}


// Bar bolan gapjygy açmak.
async function unlockTMCWallet(address, password) {
    const wallet = await getEncryptedWallet(address);

    if (!wallet) {
        throw new Error("Wallet not found in this browser.");
    }

    const privateKeyBytes = await decryptPrivateKey(
        wallet,
        password
    );

    const privateKey = await crypto.subtle.importKey(
        "pkcs8",
        privateKeyBytes,
        {
            name: "Ed25519",
        },
        false,
        ["sign"]
    );

    const publicKeyBytes = fromHex(wallet.public_key);

    const publicKey = await crypto.subtle.importKey(
        "raw",
        publicKeyBytes,
        {
            name: "Ed25519",
        },
        false,
        ["verify"]
    );

    // Hususy we açyk açarlaryň özara gabat gelýändigini barlamak.
    const challenge = new TextEncoder().encode(
        "TMC-WALLET-KEY-CHECK-V1"
    );

    const signature = await crypto.subtle.sign(
        { name: "Ed25519" },
        privateKey,
        challenge
    );

    const valid = await crypto.subtle.verify(
        { name: "Ed25519" },
        publicKey,
        signature,
        challenge
    );

    if (!valid) {
        throw new Error("Wallet key verification failed.");
    }

    return {
        address: wallet.address,
        public_key: wallet.public_key,
        privateKey: privateKey,
    };
}


// HEX maglumatyny byte görnüşine öwürmek.
function fromHex(value) {
    if (
        typeof value !== "string" ||
        value.length % 2 !== 0 ||
        !/^[0-9a-f]+$/i.test(value)
    ) {
        throw new Error("Invalid hexadecimal data.");
    }

    return Uint8Array.from(
        value.match(/.{2}/g),
        byte => parseInt(byte, 16)
    );
}


// Bar bolan gapjyk bilen hasaba alyş tranzaksiýasyna gol çekmek.
async function signWalletRegistration(wallet) {
    const transactionFields = {
        type: "register_account",
        address: wallet.address,
        public_key: wallet.public_key,
    };

    const signature = await crypto.subtle.sign(
        {
            name: "Ed25519",
        },
        wallet.privateKey,
        registrationSigningBytes(transactionFields)
    );

    return {
        ...transactionFields,
        signature: toHex(new Uint8Array(signature)),
    };
}


async function testTMCWalletRestore(address, password) {
    const wallet = await unlockTMCWallet(address, password);

    console.log("Wallet restored:", wallet.address);

    const transaction = await signWalletRegistration(wallet);

    console.log("Registration signature created:");
    console.log(transaction);

    return transaction;
}



// Gapjygyň ätiýaçlyk nusgasyny .tmcwallet faýlyna eksport etmek.
async function exportTMCWallet(address) {
    const wallet = await getEncryptedWallet(address);

    if (!wallet) {
        throw new Error("Wallet not found.");
    }

    const backup = {
        format: "TMC-WALLET-BACKUP",
        version: 1,
        exported_at: new Date().toISOString(),
        wallet: wallet
    };

    const blob = new Blob(
        [JSON.stringify(backup, null, 2)],
        { type: "application/json" }
    );

    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `${address}.tmcwallet`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);

    return true;
}




// Ätiýaçlyk nusgasyndan gapjygy import etmek.
async function importTMCWallet(file, password) {
    if (!file || !file.name.endsWith(".tmcwallet")) {
        throw new Error("Invalid TMC wallet backup file.");
    }

    const text = await file.text();
    const backup = JSON.parse(text);

    if (
        backup.format !== "TMC-WALLET-BACKUP" ||
        backup.version !== 1 ||
        !backup.wallet
    ) {
        throw new Error("Unsupported wallet backup format.");
    }

    const wallet = backup.wallet;

    if (
        !wallet.address ||
        !wallet.public_key ||
        typeof wallet.public_key !== "string"
    ) {
        throw new Error("Invalid wallet data.");
    }

    // Şifrlenen açary parol arkaly barlamak.
    const restored = await unlockWalletFromBackup(wallet, password);

    if (restored.address !== wallet.address) {
        throw new Error("Wallet address mismatch.");
    }

    // Bar bolan gapjygyň üstünden ýazmazlyk.
    const existingWallet = await getEncryptedWallet(wallet.address);

    if (existingWallet) {
        throw new Error("This wallet already exists in this browser.");
    }

    await saveImportedWallet(wallet);

    return {
        address: wallet.address,
        public_key: wallet.public_key
    };
}


// Ätiýaçlyk nusgasyndaky gapjygy açmak.
async function unlockWalletFromBackup(wallet, password) {
    const privateKeyBytes = await decryptPrivateKey(wallet, password);

    const privateKey = await crypto.subtle.importKey(
        "pkcs8",
        privateKeyBytes,
        { name: "Ed25519" },
        false,
        ["sign"]
    );

    const publicKeyBytes = fromHex(wallet.public_key);

    const publicKey = await crypto.subtle.importKey(
        "raw",
        publicKeyBytes,
        { name: "Ed25519" },
        false,
        ["verify"]
    );

    const challenge = new TextEncoder().encode(
        "TMC-WALLET-KEY-CHECK-V1"
    );

    const signature = await crypto.subtle.sign(
        "Ed25519",
        privateKey,
        challenge
    );

    const valid = await crypto.subtle.verify(
        "Ed25519",
        publicKey,
        signature,
        challenge
    );

    if (!valid) {
        throw new Error("Wallet key verification failed.");
    }

    return {
        address: wallet.address,
        public_key: wallet.public_key,
        privateKey: privateKey
    };
}


// Import edilen gapjygy IndexedDB-de saklamak.
async function saveImportedWallet(wallet) {
    const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open("TMCWalletDB", 1);

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });

    return new Promise((resolve, reject) => {
        const transaction = db.transaction(
            "wallets",
            "readwrite"
        );

        transaction.objectStore("wallets").put(wallet);

        transaction.oncomplete = () => {
            db.close();
            resolve(true);
        };

        transaction.onerror = () => {
            db.close();
            reject(transaction.error);
        };

        transaction.onabort = () => {
            db.close();
            reject(transaction.error);
        };
    });
}
