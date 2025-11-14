import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useRef, useEffect } from 'react'
import Layout from './components/layout/Layout'
import UserGuidancePage from './pages/UserGuidancePage'
import LinkInputPage from './pages/LinkInputPage'
import ScrapingProgressPage from './pages/ScrapingProgressPage'
import ResearchAgentPage from './pages/ResearchAgentPage'
import Phase3SessionPage from './pages/Phase3SessionPage'
import FinalReportPage from './pages/FinalReportPage'
import HistoryPage from './pages/HistoryPage'
import ReportExportPage from './pages/ReportExportPage'
import { useProgressNavigation } from './hooks/useProgressNavigation'

// Define route order for animation direction
const ROUTE_ORDER: Record<string, number> = {
  '/': 1,           // UserGuidancePage (NEW)
  '/links': 2,      // LinkInputPage (moved from '/')
  '/scraping': 3,
  '/research': 4,
  '/phase3': 5,
  '/report': 6,
  '/history': 0, // History is not part of the workflow
}

function AnimatedRoutes() {
  const location = useLocation()
  const prevLocationRef = useRef(location.pathname)
  useProgressNavigation() // Enable automatic navigation

  useEffect(() => {
    prevLocationRef.current = location.pathname
  }, [location.pathname])

  // Determine animation direction based on route order
  const getAnimationDirection = (): 'left' | 'right' | 'fade' => {
    const prevPath = prevLocationRef.current
    const currentPath = location.pathname

    const prevOrder = ROUTE_ORDER[prevPath] ?? 0
    const currentOrder = ROUTE_ORDER[currentPath] ?? 0

    // For history, use fade animation
    if (prevOrder === 0 || currentOrder === 0) {
      return 'fade'
    }

    return currentOrder > prevOrder ? 'left' : 'right'
  }

  const getVariants = () => {
    const direction = getAnimationDirection()

    if (direction === 'fade') {
      return {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
      }
    }

    if (direction === 'left') {
      // Forward navigation (slide left)
      return {
        initial: { opacity: 0, x: 100 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: -100 },
      }
    } else {
      // Backward navigation (slide right)
      return {
        initial: { opacity: 0, x: -100 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: 100 },
      }
    }
  }

  return (
    <AnimatePresence mode="wait">
      <Routes location={location}>
        <Route
          path="/"
          element={
            <motion.div
              key="page-guidance"
              initial="initial"
              animate="animate"
              exit="exit"
              variants={getVariants()}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="h-full"
            >
              <UserGuidancePage />
            </motion.div>
          }
        />
        <Route
          path="/links"
          element={
            <motion.div
              key="page-links"
              initial="initial"
              animate="animate"
              exit="exit"
              variants={getVariants()}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="h-full"
            >
              <LinkInputPage />
            </motion.div>
          }
        />
        <Route
          path="/scraping"
          element={
            <motion.div
              key="page-2"
              initial="initial"
              animate="animate"
              exit="exit"
              variants={getVariants()}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="h-full"
            >
              <ScrapingProgressPage />
            </motion.div>
          }
        />
        <Route
          path="/research"
          element={
            <motion.div
              key="page-3"
              initial="initial"
              animate="animate"
              exit="exit"
              variants={getVariants()}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="h-full"
            >
              <ResearchAgentPage />
            </motion.div>
          }
        />
        <Route
          path="/phase3"
          element={
            <motion.div
              key="page-4"
              initial="initial"
              animate="animate"
              exit="exit"
              variants={getVariants()}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="h-full"
            >
              <Phase3SessionPage />
            </motion.div>
          }
        />
        <Route
          path="/report"
          element={
            <motion.div
              key="page-5"
              initial="initial"
              animate="animate"
              exit="exit"
              variants={getVariants()}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className="h-full"
            >
              <FinalReportPage />
            </motion.div>
          }
        />
        <Route
          path="/history"
          element={
            <motion.div
              key="page-history"
              initial="initial"
              animate="animate"
              exit="exit"
              variants={getVariants()}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <HistoryPage />
            </motion.div>
          }
        />
        <Route
          path="/export/:sessionId"
          element={<ReportExportPage />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <AnimatedRoutes />
      </Layout>
    </BrowserRouter>
  )
}

export default App


