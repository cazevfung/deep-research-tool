import { useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useWorkflowStore } from '../stores/workflowStore'
import { useCurrentActiveStep } from './useWorkflowStep'

const STEP_ROUTES: Record<number, string> = {
  1: '/',
  2: '/scraping',
  3: '/research',
  4: '/phase3',
  5: '/report',
}

/**
 * Hook to automatically navigate to the current active step based on workflow progress
 */
export const useProgressNavigation = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const currentActiveStep = useCurrentActiveStep()
  const {
    batchId,
    scrapingStatus,
    cancelled,
    researchAgentStatus,
    phase3Steps,
    finalReport,
  } = useWorkflowStore()

  // Track if we've already navigated to avoid loops
  const lastNavigatedStepRef = useRef<number | null>(null)
  const navigationTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  
  // Track manual navigation to temporarily disable auto-navigation
  const manualNavigationRef = useRef<{ route: string; timestamp: number } | null>(null)
  const lastRouteRef = useRef<string>(location.pathname)
  const MANUAL_NAV_DISABLE_DURATION = 2000 // Disable auto-nav for 2 seconds after manual nav

  // Detect manual navigation by watching route changes
  useEffect(() => {
    const currentRoute = location.pathname
    const expectedRoute = STEP_ROUTES[currentActiveStep]
    
    // If route changed and doesn't match expected step, it's likely manual navigation
    if (currentRoute !== lastRouteRef.current && currentRoute !== expectedRoute) {
      // Check if this route is a valid workflow route (not history, export, etc.)
      const isValidWorkflowRoute = Object.values(STEP_ROUTES).includes(currentRoute)
      
      if (isValidWorkflowRoute) {
        console.log(`Manual navigation detected to: ${currentRoute} (expected: ${expectedRoute})`)
        manualNavigationRef.current = {
          route: currentRoute,
          timestamp: Date.now()
        }
      }
    }
    
    lastRouteRef.current = currentRoute
  }, [location.pathname, currentActiveStep])

  useEffect(() => {
    // Don't navigate if no batchId (still on initial step)
    if (!batchId && currentActiveStep === 1) {
      lastNavigatedStepRef.current = 1
      return
    }

    const currentRoute = location.pathname
    const expectedRoute = STEP_ROUTES[currentActiveStep]
    
    // Check if we're currently on a route that doesn't match the expected step
    // This indicates manual navigation that we should respect
    if (currentRoute !== expectedRoute && Object.values(STEP_ROUTES).includes(currentRoute)) {
      // User manually navigated to a different phase - respect this choice
      console.log(`Respecting manual navigation to ${currentRoute} (expected step ${currentActiveStep}: ${expectedRoute})`)
      
      // Record this as manual navigation
      manualNavigationRef.current = {
        route: currentRoute,
        timestamp: Date.now()
      }
      
      // Update lastNavigatedStepRef to prevent auto-nav until state changes
      const routeToStep = Object.entries(STEP_ROUTES).find(([_, route]) => route === currentRoute)?.[0]
      if (routeToStep) {
        lastNavigatedStepRef.current = parseInt(routeToStep)
      }
      
      return
    }

    // Check if manual navigation happened recently - if so, disable auto-navigation
    if (manualNavigationRef.current) {
      const timeSinceManualNav = Date.now() - manualNavigationRef.current.timestamp
      if (timeSinceManualNav < MANUAL_NAV_DISABLE_DURATION) {
        // Manual navigation happened recently, don't auto-navigate
        console.log(`Auto-navigation disabled due to recent manual navigation (${timeSinceManualNav}ms ago)`)
        return
      } else {
        // Manual navigation window expired, clear it
        manualNavigationRef.current = null
      }
    }

    // Don't navigate if we've already navigated to this step
    if (lastNavigatedStepRef.current === currentActiveStep) {
      return
    }

    // Clear any pending navigation
    if (navigationTimeoutRef.current) {
      clearTimeout(navigationTimeoutRef.current)
    }

    // Debounce navigation to avoid rapid changes
    navigationTimeoutRef.current = setTimeout(() => {
      const targetRoute = STEP_ROUTES[currentActiveStep]
      if (targetRoute) {
        // Only navigate if we're not already on the target route
        if (window.location.pathname !== targetRoute) {
          console.log(`Auto-navigating to step ${currentActiveStep}: ${targetRoute}`)
          navigate(targetRoute, { replace: true })
          lastNavigatedStepRef.current = currentActiveStep
        }
      }
    }, 300) // Small delay to batch rapid state changes

    return () => {
      if (navigationTimeoutRef.current) {
        clearTimeout(navigationTimeoutRef.current)
      }
    }
  }, [currentActiveStep, navigate, batchId, location.pathname])

  // Reset navigation tracking when batchId changes (new session)
  useEffect(() => {
    if (!batchId) {
      lastNavigatedStepRef.current = null
      manualNavigationRef.current = null
    }
  }, [batchId])
}




