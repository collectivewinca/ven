// Firebase configuration
// The app uses Firestore REST API directly (no SDK needed).
// Project ID and API key are read from VITE_FIREBASE_* env vars in App.tsx.
//
// This file is kept as a reference for the Firebase project configuration.
// If you need the Firestore SDK in the future, uncomment the imports below.

// import { initializeApp } from "firebase/app";
// import { getFirestore } from "firebase/firestore";
// import { getAnalytics } from "firebase/analytics";
//
// const firebaseConfig = {
//   apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
//   authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "miny-ven.firebaseapp.com",
//   projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "miny-ven",
//   storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "miny-ven.appspot.com",
//   messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
//   appId: import.meta.env.VITE_FIREBASE_APP_ID,
//   measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
// };
//
// const app = initializeApp(firebaseConfig);
// export const db = getFirestore(app);
// export const analytics = typeof window !== 'undefined' ? getAnalytics(app) : null;
// export default app;
