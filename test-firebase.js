const { initializeApp } = require('firebase/app');
const { getFirestore, collection, query, orderBy, limit, getDocs } = require('firebase/firestore');

const firebaseConfig = {
  apiKey: "AIzaSyCD7B4GDaRypsBGWODRyhxiGXnFUbAehfM",
  authDomain: "miny-ven.firebaseapp.com",
  projectId: "miny-ven",
  storageBucket: "miny-ven.firebasestorage.app",
  messagingSenderId: "1055083577389",
  appId: "1:1055083577389:web:11509efe18dec3477bf8a4",
  measurementId: "G-ECJHS6PSR4"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

async function testFetch() {
  try {
    console.log('Testing Firestore connection...');
    const q = query(
      collection(db, 'articles'),
      orderBy('published_at', 'desc'),
      limit(50)
    );
    
    const snapshot = await getDocs(q);
    console.log(`Found ${snapshot.size} articles`);
    
    snapshot.forEach(doc => {
      console.log(`- ${doc.data().title}`);
    });
  } catch (error) {
    console.error('Error:', error.message);
    console.error('Code:', error.code);
  }
}

testFetch();
