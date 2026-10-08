# Copyright (c) 2026 Hao Jiang
# SPDX-License-Identifier: MIT
# Run with VMD from the private Input directory.
source [file join [file dirname [info script]] selection.tcl]
if {$qmRegion1Selection eq "none"} {
    error "Set qmRegion1Selection in selection.tcl before preparing a calculation."
}
set molid [mol new $inputPSF waitfor all]
mol addfile $inputPDB molid $molid waitfor all
set all [atomselect $molid all]
set qm [atomselect $molid $qmRegion1Selection]
if {[$qm num] == 0} {error "QM selection is empty."}
$all set beta 0
$all set occupancy 0
$qm set beta 1
set declared [list]
foreach entry $qmMmLinkBonds {
    if {[llength $entry] != 3} {error "Boundary entries require a label and two selections."}
    lassign $entry label qexpr mexpr
    set q [atomselect $molid $qexpr]
    set m [atomselect $molid $mexpr]
    if {[$q num] != 1 || [$m num] != 1} {error "Boundary $label must have one atom at each end."}
    if {[lindex [$q get beta] 0] != 1 || [lindex [$m get beta] 0] != 0} {
        error "Boundary $label does not connect a QM atom to an MM atom."
    }
    set qi [lindex [$q get index] 0]
    set mi [lindex [$m get index] 0]
    if {[lsearch -exact [lindex [$q getbonds] 0] $mi] < 0} {
        error "Boundary $label is absent from the PSF bonds."
    }
    set pair [lsort -integer [list $qi $mi]]
    if {[lsearch -exact $declared $pair] >= 0} {error "Duplicate boundary $label."}
    lappend declared $pair
    $q set occupancy 1
    $m set occupancy 1
    $q delete
    $m delete
}
# Every PSF bond crossing the selected boundary must be accounted for.
set qmids [$qm get index]
set actual [list]
foreach qi $qmids neighbors [$qm getbonds] {
    foreach mi $neighbors {
        if {[lsearch -exact $qmids $mi] < 0} {
            lappend actual [lsort -integer [list $qi $mi]]
        }
    }
}
if {[lsort -unique $declared] ne [lsort -unique $actual]} {
    error "Declared boundaries do not match the PSF bonds crossing the QM selection."
}
package require topotools
topo guessatom element mass
$all writepdb ref-qm_mm
$qm writepsf qm.psf
set output [open qm.list w]
set i 0
foreach atomid $qmids {puts $output "$i $atomid"; incr i}
close $output
# Select all MM sites for embedding, independently of mobility.
$all set beta 0
$all set occupancy 1
$qm set beta 1
$qm set occupancy 0
$all writepdb ref-point_charge
# Mobility flags use their own file; preserve the original molecule/topology.
set active [atomselect $molid $activeSelection]
if {[$active num] == 0} {error "Active selection is empty."}
set activeids [$active get index]
foreach atomid $qmids {
    if {[lsearch -exact $activeids $atomid] < 0} {
        error "A QM atom is outside the active selection. Review activeSelection."
    }
}
$all set beta 1
$all set occupancy 0
$active set beta 0
$all writepdb ref-active
puts "Prepared [$qm num] QM atoms, [llength $actual] boundary bonds, and [$active num] movable atoms."
$active delete
$qm delete
$all delete
mol delete $molid
quit
