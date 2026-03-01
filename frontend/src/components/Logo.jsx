import React from 'react';

export default function Logo({ size = 32, className = '' }) {
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 64 64"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className={className}
        >
            {/* Glow filters */}
            <defs>
                <filter id="glowBlue" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="2" result="blur" />
                    <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                    </feMerge>
                </filter>
                <filter id="glowGreen" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="1.5" result="blur" />
                    <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                    </feMerge>
                </filter>
                <linearGradient id="blueGrad" x1="0" y1="0" x2="0.5" y2="1">
                    <stop offset="0%" stopColor="#60a5fa" />
                    <stop offset="100%" stopColor="#3b82f6" />
                </linearGradient>
                <linearGradient id="greenGrad" x1="0.5" y1="0" x2="0.5" y2="1">
                    <stop offset="0%" stopColor="#4ade80" />
                    <stop offset="100%" stopColor="#22c55e" />
                </linearGradient>
            </defs>

            {/* W shape — left portion (blue neon) */}
            <polyline
                points="8,16 18,48 28,28 32,38"
                stroke="url(#blueGrad)"
                strokeWidth="4"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
                filter="url(#glowBlue)"
            />

            {/* W shape — right portion connecting to pencil (blue neon) */}
            <polyline
                points="32,38 38,20"
                stroke="url(#blueGrad)"
                strokeWidth="4"
                strokeLinecap="round"
                strokeLinejoin="round"
                fill="none"
                filter="url(#glowBlue)"
            />

            {/* Pencil body (green neon) */}
            <g filter="url(#glowGreen)">
                {/* Pencil shaft */}
                <line x1="38" y1="20" x2="50" y2="52" stroke="url(#greenGrad)" strokeWidth="4" strokeLinecap="round" />
                {/* Pencil tip */}
                <polygon points="50,52 47,56 53,56" fill="#22c55e" />
                {/* Pencil eraser band */}
                <line x1="39.5" y1="24" x2="42" y2="23" stroke="#a3e635" strokeWidth="2" strokeLinecap="round" />
                {/* Eraser top */}
                <rect x="36" y="15" width="6" height="5" rx="1.5" fill="#a3a3a3" stroke="#737373" strokeWidth="0.5" />
            </g>
        </svg>
    );
}
