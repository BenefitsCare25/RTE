/**
 * IndexedDB-based recovery storage for enrichment sessions.
 * Stores processed companies progressively to enable recovery after disruptions.
 */

export interface EnrichedCompany {
  name: string;
  uen: string;
  address: string;
  phone_1: string;
  phone_2: string;
  phone_3: string;
  email: string;
  website: string;
  status: string;
}

export interface RecoverySession {
  sessionId: string;
  originalFilename: string;
  totalCompanies: number;
  processedCompanies: EnrichedCompany[];
  startedAt: number;
  lastUpdatedAt: number;
  status: 'in_progress' | 'interrupted' | 'complete';
}

const DB_NAME = 'enrichment-recovery';
const DB_VERSION = 1;
const STORE_NAME = 'sessions';

class RecoveryStorage {
  private db: IDBDatabase | null = null;
  private initPromise: Promise<void> | null = null;

  /**
   * Initialize IndexedDB connection
   */
  async init(): Promise<void> {
    if (this.db) return;
    if (this.initPromise) return this.initPromise;

    this.initPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onerror = () => {
        console.error('Failed to open IndexedDB:', request.error);
        reject(request.error);
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: 'sessionId' });
          store.createIndex('status', 'status', { unique: false });
        }
      };
    });

    return this.initPromise;
  }

  /**
   * Save a new session or update existing one
   */
  async saveSession(session: RecoverySession): Promise<void> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.put(session);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Add a processed company to an existing session
   */
  async addProcessedCompany(sessionId: string, company: EnrichedCompany): Promise<void> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const getRequest = store.get(sessionId);

      getRequest.onsuccess = () => {
        const session = getRequest.result as RecoverySession | undefined;
        if (!session) {
          reject(new Error('Session not found'));
          return;
        }

        session.processedCompanies.push(company);
        session.lastUpdatedAt = Date.now();

        const putRequest = store.put(session);
        putRequest.onsuccess = () => resolve();
        putRequest.onerror = () => reject(putRequest.error);
      };

      getRequest.onerror = () => reject(getRequest.error);
    });
  }

  /**
   * Get the most recent incomplete session (in_progress or interrupted)
   */
  async getIncompleteSession(): Promise<RecoverySession | null> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_NAME], 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.getAll();

      request.onsuccess = () => {
        const sessions = request.result as RecoverySession[];
        // Find incomplete sessions (in_progress or interrupted)
        const incomplete = sessions.filter(
          (s) => s.status === 'in_progress' || s.status === 'interrupted'
        );

        if (incomplete.length === 0) {
          resolve(null);
          return;
        }

        // Return most recent
        incomplete.sort((a, b) => b.lastUpdatedAt - a.lastUpdatedAt);
        resolve(incomplete[0]);
      };

      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Mark a session as interrupted
   */
  async markInterrupted(sessionId: string): Promise<void> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const getRequest = store.get(sessionId);

      getRequest.onsuccess = () => {
        const session = getRequest.result as RecoverySession | undefined;
        if (!session) {
          resolve(); // Session might already be cleared
          return;
        }

        session.status = 'interrupted';
        session.lastUpdatedAt = Date.now();

        const putRequest = store.put(session);
        putRequest.onsuccess = () => resolve();
        putRequest.onerror = () => reject(putRequest.error);
      };

      getRequest.onerror = () => reject(getRequest.error);
    });
  }

  /**
   * Mark a session as complete
   */
  async markComplete(sessionId: string): Promise<void> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const getRequest = store.get(sessionId);

      getRequest.onsuccess = () => {
        const session = getRequest.result as RecoverySession | undefined;
        if (!session) {
          resolve();
          return;
        }

        session.status = 'complete';
        session.lastUpdatedAt = Date.now();

        const putRequest = store.put(session);
        putRequest.onsuccess = () => resolve();
        putRequest.onerror = () => reject(putRequest.error);
      };

      getRequest.onerror = () => reject(getRequest.error);
    });
  }

  /**
   * Clear/delete a session
   */
  async clearSession(sessionId: string): Promise<void> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_NAME], 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.delete(sessionId);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  /**
   * Get session by ID
   */
  async getSession(sessionId: string): Promise<RecoverySession | null> {
    await this.init();
    if (!this.db) throw new Error('Database not initialized');

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction([STORE_NAME], 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.get(sessionId);

      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }
}

// Export singleton instance
export const recoveryStorage = new RecoveryStorage();
