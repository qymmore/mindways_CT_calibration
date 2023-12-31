#####
# ogo_helper.py
#
# This script contains functions to be used in the Ogo Calibration and Finite Element
# Analysis process
#
#####
#
# Andrew Michalski
# University of Calgary
# Biomedical Engineering Graduate Program
# April 23, 2019
# Modified to Py3: March 25, 2020
#####

##
# Import the modules for the functions
import os
import sys
import time
import datetime
import math
import pandas as pd
import numpy as np
from scipy import stats
import scipy.interpolate as interp
import SimpleITK as sitk
import vtk
import vtkbone
from vtkmodules.util.numpy_support import vtk_to_numpy, numpy_to_vtk
#from vtk.Wrapping.Python.vtkmodules.util.numpy_support import vtk_to_numpy, numpy_to_vtk
from collections import OrderedDict

start_time = time.time()

##
# Functions for Ogo Calibration Scripts
def applyInternalCalibration(imageData, cali_parameters):
    """ Applies the internal calibration to the image.
    The first argument is the image.
    The second argument is a dictionary of the calibration parameters.
    Returns the calibrated image in mg/cc.
    """
    ##
    # Some parameters to have from the inputs
    extent = imageData.GetExtent()
    origin = imageData.GetOrigin()
    spacing = imageData.GetSpacing()
    voxel_volume_mm = spacing[0] * spacing[1] * spacing[2] # [mm^3]
    voxel_volume_cm = voxel_volume_mm / 1000 # [cm^3]
    HU_MassAtten_Slope = cali_parameters['HU-u/p Slope']
    HU_MassAtten_Yint = cali_parameters['HU-u/p Y-Intercept']
    HU_Den_Slope = cali_parameters['HU-Material Density Slope']
    HU_Den_Yint = cali_parameters['HU-Material Density Y-Intercept']
    Triglyceride_Mass_Atten = cali_parameters['Triglyceride u/p']
    K2HPO4_Mass_Atten = cali_parameters['K2HPO4 u/p']

    ##
    # Create copies of the image data for Output density Images and convert to numpy arrays
    # Mass Attenuation Reference Image
    Mass_Atten_image = vtk.vtkImageData()
    Mass_Atten_image.SetExtent(extent)
    Mass_Atten_image.SetOrigin(origin)
    Mass_Atten_image.SetSpacing(spacing)
    Mass_Atten_image.AllocateScalars(vtk.VTK_FLOAT, 1)
    Mass_Atten_data = vtk2numpy(Mass_Atten_image)

    # Archimedian Density Reference Image
    Arch_den_image = vtk.vtkImageData()
    Arch_den_image.SetExtent(extent)
    Arch_den_image.SetOrigin(origin)
    Arch_den_image.SetSpacing(spacing)
    Arch_den_image.AllocateScalars(vtk.VTK_FLOAT, 1)
    Arch_den_data = vtk2numpy(Arch_den_image)

    # Mass Attenuation Reference Image
    Mass_image = vtk.vtkImageData()
    Mass_image.SetExtent(extent)
    Mass_image.SetOrigin(origin)
    Mass_image.SetSpacing(spacing)
    Mass_image.AllocateScalars(vtk.VTK_FLOAT, 1)
    Mass_data = vtk2numpy(Mass_image)

    # K2HPO4 Density
    K2HPO4_den_image = vtk.vtkImageData()
    K2HPO4_den_image.SetExtent(extent)
    K2HPO4_den_image.SetOrigin(origin)
    K2HPO4_den_image.SetSpacing(spacing)
    K2HPO4_den_image.AllocateScalars(vtk.VTK_FLOAT, 1)
    K2HPO4_den_data = vtk2numpy(K2HPO4_den_image)

    ##
    # Convert image to NumPy
    message("Converting image to NumPy...")
    numpy_image = vtk2numpy(imageData)

    ##
    # Apply HU to Mass Attenuation Conversion
    message("Converting image to mass attenuation equivalent...")
    Mass_Atten_data[:,:,:] = ((HU_MassAtten_Slope * numpy_image) + HU_MassAtten_Yint)

    # Apply HU to Archimedian Density Conversion
    message("Converting image to Archimedian density equivalent...")
    Arch_den_data[:,:,:] = ((HU_Den_Slope * numpy_image) + HU_Den_Yint)

    # Convert Archimedian density to total mass equivalent
    message("Converting Archimedian density equivalent to Mass equivalent image...")
    Mass_data[:,:,:] = Arch_den_data * voxel_volume_cm

    # Converting onverting to K2HPO4 Mass
    message("Converting to K2HPO4 Mass Image...")
    K2HPO4_mass_seg_data = np.zeros_like(Mass_data, dtype = 'h')

    # Two component model to derive K2HPO4 mass image
    K2HPO4_mass_seg_data = (Mass_data *((Mass_Atten_data - Triglyceride_Mass_Atten) / (K2HPO4_Mass_Atten - Triglyceride_Mass_Atten)))

    # Converting mass images to density images
    message("Converting K2HPO4 mass images to K2HPO4 density images...")
    K2HPO4_den_data = K2HPO4_mass_seg_data / voxel_volume_cm * 1000 # *1000 to convert g to mg

    # Convery Numpy images back to vtk Image
    scalars = K2HPO4_den_data.flatten(order='C')
    VTK_data = numpy_to_vtk(num_array=scalars, deep=True, array_type=vtk.VTK_FLOAT)
    K2HPO4_den_image.GetPointData().SetScalars(VTK_data)

    return K2HPO4_den_image

def applyMask(imageData, maskData):
    """Applies the mask to the image.
    The first argument is the image. The second argument is the mask.
    Returns the masked image as image Data.
    """
    mask = vtk.vtkImageMask()
    mask.SetMaskedOutputValue(0)
    mask.SetImageInputData(imageData)
    mask.SetMaskInputData(maskData)
    mask.NotMaskOff()
    mask.Update()
    return mask.GetOutput()

def applyPhantomParameters(vtk_image, calibration_parameters):
    """Uses image mathematics to apply image calibration.
    The first argument is the vtk Image Data.
    The second argument are the calibration parameters dictionary (slope, y-intercept).
    Returns vtk Image Data in FLOAT data type.
    """
    cast = vtk.vtkImageCast()
    cast.SetInputData(vtk_image)
    cast.SetOutputScalarTypeToFloat()
    cast.Update()

    slope_image = vtk.vtkImageMathematics()
    slope_image.SetInputConnection(0, cast.GetOutputPort())
    slope_image.SetOperationToMultiplyByK()
    slope_image.SetConstantK(calibration_parameters['Calibration Slope'])
    slope_image.Update()

    calibrated_image = vtk.vtkImageMathematics()
    calibrated_image.SetInputConnection(0, slope_image.GetOutputPort())
    calibrated_image.SetOperationToAddConstant()
    calibrated_image.SetConstantC(calibration_parameters['Calibration Y-Intercept'])
    calibrated_image.Update()

    return calibrated_image.GetOutput()

def applyTestBase(mesh, material_table):
    """Constructs to the FEM object.
    The first argument is the Image Mesh.
    The second argument is the material table.
    Returns the model output.
    """
    generator = vtkbone.vtkboneFiniteElementModelGenerator()
    generator.SetInputData(0, mesh)
    generator.SetInputData(1, material_table)
    generator.Update()

    return generator.GetOutput()

def applyTransform(vtk_image, matrix):
    """Applies the transform matrix to the image.
    The first argument is the vtk image data.
    The second argument is the 4x4 rotation matrix.
    Returns the transformed image.
    """
    transform = vtk.vtkTransform()
    transform.SetMatrix(matrix)
    transform.Update()

    reslice = vtk.vtkImageReslice()
    reslice.SetInputData(vtk_image)
    reslice.SetInterpolationModeToCubic()
    reslice.SetResliceTransform(transform)
    reslice.AutoCropOutputOn()
    reslice.Update()

    return reslice.GetOutput()

def bmd_CHAToAsh(vtk_image):
    """Converts CHA density to ash density using equation from:
    CHA density to ASH density relationship from Kaneko et al. 2004 J Biomech
    'Mechanical properties, density and quantitative CT scan data of trabecular
        bone with and without metastases'
    The first argument is the density image.
    Returns the Ash Density Image.
    """
    slope_image = vtk.vtkImageMathematics()
    slope_image.SetInputData(0, vtk_image)
    slope_image.SetOperationToMultiplyByK()
    slope_image.SetConstantK(0.839)
    slope_image.Update()

    calibrated_image = vtk.vtkImageMathematics()
    calibrated_image.SetInputConnection(0, slope_image.GetOutputPort())
    calibrated_image.SetOperationToAddConstant()
    calibrated_image.SetConstantC(69.8)
    calibrated_image.Update()
    return calibrated_image.GetOutput()

def bmd_K2hpo4ToAsh(vtk_image):
    """Converts K2HPO4 density to ash density using equation from:
    K2HPO4 density to ASH density relationship from Keyak et al. J Biomed Mater Res
    1994 "Correlations between orthogonal mechanical properties and density of trabecular
    bone use of different densitometric measures.
    The first argument is the density image.
    Returns the Ash Density Image.
    """
    slope_image = vtk.vtkImageMathematics()
    slope_image.SetInputData(0, vtk_image)
    slope_image.SetOperationToMultiplyByK()
    slope_image.SetConstantK(1.06)
    slope_image.Update()

    calibrated_image = vtk.vtkImageMathematics()
    calibrated_image.SetInputConnection(0, slope_image.GetOutputPort())
    calibrated_image.SetOperationToAddConstant()
    calibrated_image.SetConstantC(38.9)
    calibrated_image.Update()
    return calibrated_image.GetOutput()

def bmd_metrics(vtk_image):
    """Computes the BMD metrics for the input vtk image. VTK image should be the isolated
    bone VOI (from applyMask). First, converts to numpy. Analysis performed in Numpy. The
    first argument is the vtk Image Data.
    Returns dictionary of results.
    """
    spacing = vtk_image.GetSpacing()
    numpy_image = vtk2numpy(vtk_image)
    voxel_count = np.count_nonzero(numpy_image)
    voxel_volume = spacing[0] * spacing[1] * spacing[2]  # [mm^3]
    voxel_volume2 = voxel_volume / 1000  # [cm^3]

    # BMD measures
    BMD_total = numpy_image.sum()  # [mg/cc K2HPO4]
    BMD_AVG = BMD_total / voxel_count  # [mg/cc K2HPO4]
    VOLUME_mm = voxel_count * voxel_volume
    VOLUME_cm = voxel_count * voxel_volume2  # [cm^3]
    BMC = BMD_AVG * VOLUME_cm  # [mg HA]

    return {
    'Integral BMD [mg/cc]':BMD_AVG,
    'Integral BMC [mg]':BMC,
    'Bone Volume [mm^3]':VOLUME_mm,
    'Bone Volume [cm^3]':VOLUME_cm
    }

def bmd_preprocess(vtk_image, thresh_value):
    """Preprocess the calibrated image to remove densities less than 0 mg/cc
    and replace the value with minimum equivalent E value of 0.1 MPa.
    The first argument is the vtk Image data of the calibrated image.
    Returns vtk Image data.
    """
    threshold = vtk.vtkImageThreshold()
    threshold.SetInputData(vtk_image)
    threshold.ThresholdByLower(thresh_value)
    threshold.ReplaceInOn()
    threshold.SetInValue(thresh_value)
    threshold.ReplaceOutOff()
    threshold.Update()
    return threshold.GetOutput()

def cast2short(vtk_image):
    """Cast image data to Short"""
    cast = vtk.vtkImageCast()
    cast.SetInputData(vtk_image)
    cast.SetOutputScalarTypeToShort()
    cast.Update()
    return cast.GetOutput()

def cast2unsignchar(vtk_image):
    """Cast Image Data to Unsigned Char"""
    cast = vtk.vtkImageCast()
    cast.SetInputData(vtk_image)
    cast.SetOutputScalarTypeToUnsignedChar()
    cast.Update()
    return cast.GetOutput()

def changeInfo(vtk_image):
    """Changes the origin of image to 0,0,0"""
    change = vtk.vtkImageChangeInformation()
    change.SetInputData(vtk_image)
    change.SetOutputOrigin(0,0,0)
    change.Update()
    return change.GetOutput()

def combineImageData_SF(image, fh_pmma_id_pad, gt_pmma_id_pad, pmma_mat_id):
    """Combines the 3 image data together to get final image.
    The first argument is the original image data.
    The second argument is the femoral head PMMA cap image.
    The third argument is the greater trochanter PMMA cap image.
    Returns the combined image data.
    """
    message("Padding the images to constant size...")
    ##
    # Pad all images so that they are the same size
    fh_pad = vtk.vtkImageConstantPad()
    fh_pad.SetInputData(fh_pmma_id_pad)
    fh_pad.SetOutputWholeExtent(image.GetExtent())
    fh_pad.SetConstant(0)
    fh_pad.Update()

    gt_pad = vtk.vtkImageConstantPad()
    gt_pad.SetInputData(gt_pmma_id_pad)
    gt_pad.SetOutputWholeExtent(image.GetExtent())
    gt_pad.SetConstant(0)
    gt_pad.Update()

    message("Combining PMMA Caps with Image Data...")
    fh_logic = vtk.vtkImageLogic()
    fh_logic.SetInput1Data(fh_pad.GetOutput())
    fh_logic.SetInput2Data(image)
    fh_logic.SetOperationToAnd()
    fh_logic.SetOutputTrueValue(pmma_mat_id)
    fh_logic.Update()

    fh_math = vtk.vtkImageMathematics()
    fh_math.SetInput1Data(fh_pad.GetOutput())
    fh_math.SetInput2Data(fh_logic.GetOutput())
    fh_math.SetOperationToSubtract()
    fh_math.Update()

    combo_image = vtk.vtkImageMathematics()
    combo_image.SetInput1Data(fh_math.GetOutput())
    combo_image.SetInput2Data(image)
    combo_image.SetOperationToAdd()
    combo_image.Update()

    gt_logic = vtk.vtkImageLogic()
    gt_logic.SetInput1Data(gt_pad.GetOutput())
    gt_logic.SetInput2Data(image)
    gt_logic.SetOperationToAnd()
    gt_logic.SetOutputTrueValue(pmma_mat_id)
    gt_logic.Update()

    gt_math = vtk.vtkImageMathematics()
    gt_math.SetInput1Data(gt_pad.GetOutput())
    gt_math.SetInput2Data(gt_logic.GetOutput())
    gt_math.SetOperationToSubtract()
    gt_math.Update()

    combo_image2 = vtk.vtkImageMathematics()
    combo_image2.SetInput1Data(gt_math.GetOutput())
    combo_image2.SetInput2Data(combo_image.GetOutput())
    combo_image2.SetOperationToAdd()
    combo_image2.Update()

    message("PMMA caps added.")
    message("Creating final image...")
    # Remove any negative values...
    final_thres = vtk.vtkImageThreshold()
    final_thres.SetInputData(combo_image2.GetOutput())
    final_thres.ThresholdByLower(0)
    final_thres.ReplaceInOn()
    final_thres.SetInValue(0)
    final_thres.ReplaceOutOff()
    final_thres.Update()
    final_image = final_thres.GetOutput()

    return final_image

def combineImageData_SLS(image, fh_pmma_id_pad, pmma_mat_id):
    """Combines the 2 image data together to get final image.
    The first argument is the original image data.
    The second argument is the femoral head PMMA cap image.
    The third argument is the greater trochanter PMMA cap image.
    Returns the combined image data.
    """
    message("Padding the images to constant size...")
    ##
    # Pad all images so that they are the same size
    fh_pad = vtk.vtkImageConstantPad()
    fh_pad.SetInputData(fh_pmma_id_pad)
    fh_pad.SetOutputWholeExtent(image.GetExtent())
    fh_pad.SetConstant(0)
    fh_pad.Update()

    message("Combining PMMA Caps with Image Data...")
    fh_logic = vtk.vtkImageLogic()
    fh_logic.SetInput1Data(fh_pad.GetOutput())
    fh_logic.SetInput2Data(image)
    fh_logic.SetOperationToAnd()
    fh_logic.SetOutputTrueValue(pmma_mat_id)
    fh_logic.Update()

    fh_math = vtk.vtkImageMathematics()
    fh_math.SetInput1Data(fh_pad.GetOutput())
    fh_math.SetInput2Data(fh_logic.GetOutput())
    fh_math.SetOperationToSubtract()
    fh_math.Update()

    combo_image = vtk.vtkImageMathematics()
    combo_image.SetInput1Data(fh_math.GetOutput())
    combo_image.SetInput2Data(image)
    combo_image.SetOperationToAdd()
    combo_image.Update()

    message("PMMA caps added.")
    message("Creating final image...")
    # Remove any negative values...
    final_thres = vtk.vtkImageThreshold()
    final_thres.SetInputData(combo_image.GetOutput())
    final_thres.ThresholdByLower(0)
    final_thres.ReplaceInOn()
    final_thres.SetInValue(0)
    final_thres.ReplaceOutOff()
    final_thres.Update()
    final_image = final_thres.GetOutput()

    return final_image

def combineImageData_VC(image, sup_pmma_id_pad, inf_pmma_id_pad, pmma_mat_id):
    """Combines the 3 image data together to get final image.
    The first argument is the original image data.
    The second argument is the superior PMMA cap image.
    The third argument is the inferior PMMA cap image.
    Returns the combined image data.
    """
    message("Padding the images to constant size...")
    ##
    # Pad all images so that they are the same size
    sup_pad = vtk.vtkImageConstantPad()
    sup_pad.SetInputData(sup_pmma_id_pad)
    sup_pad.SetOutputWholeExtent(image.GetExtent())
    sup_pad.SetConstant(0)
    sup_pad.Update()

    inf_pad = vtk.vtkImageConstantPad()
    inf_pad.SetInputData(inf_pmma_id_pad)
    inf_pad.SetOutputWholeExtent(image.GetExtent())
    inf_pad.SetConstant(0)
    inf_pad.Update()

    message("Combining PMMA Caps with Image Data...")
    sup_logic = vtk.vtkImageLogic()
    sup_logic.SetInput1Data(sup_pad.GetOutput())
    sup_logic.SetInput2Data(image)
    sup_logic.SetOperationToAnd()
    sup_logic.SetOutputTrueValue(pmma_mat_id)
    sup_logic.Update()

    sup_math = vtk.vtkImageMathematics()
    sup_math.SetInput1Data(sup_pad.GetOutput())
    sup_math.SetInput2Data(sup_logic.GetOutput())
    sup_math.SetOperationToSubtract()
    sup_math.Update()

    combo_image = vtk.vtkImageMathematics()
    combo_image.SetInput1Data(sup_math.GetOutput())
    combo_image.SetInput2Data(image)
    combo_image.SetOperationToAdd()
    combo_image.Update()

    inf_logic = vtk.vtkImageLogic()
    inf_logic.SetInput1Data(inf_pad.GetOutput())
    inf_logic.SetInput2Data(image)
    inf_logic.SetOperationToAnd()
    inf_logic.SetOutputTrueValue(pmma_mat_id)
    inf_logic.Update()

    inf_math = vtk.vtkImageMathematics()
    inf_math.SetInput1Data(inf_pad.GetOutput())
    inf_math.SetInput2Data(inf_logic.GetOutput())
    inf_math.SetOperationToSubtract()
    inf_math.Update()

    combo_image2 = vtk.vtkImageMathematics()
    combo_image2.SetInput1Data(inf_math.GetOutput())
    combo_image2.SetInput2Data(combo_image.GetOutput())
    combo_image2.SetOperationToAdd()
    combo_image2.Update()

    message("PMMA caps added.")
    message("Creating final image...")
    # Remove any negative values...
    final_thres = vtk.vtkImageThreshold()
    final_thres.SetInputData(combo_image2.GetOutput())
    final_thres.ThresholdByLower(0)
    final_thres.ReplaceInOn()
    final_thres.SetInValue(0)
    final_thres.ReplaceOutOff()
    final_thres.Update()
    final_image = final_thres.GetOutput()

    return final_image

def extractBox(extraction_bounds, model):
    """Extracts the geometry within the specific bounds.
    The first argument are the extraction bounds of the box.
    The second arument is the geometry to be extracted.
    Returns the extracted geometry.
    """
    box = vtk.vtkBox()
    box.SetBounds(extraction_bounds)

    geometry = vtk.vtkExtractGeometry()
    geometry.SetInputData(0, model)
    geometry.SetImplicitFunction(box)
    geometry.ExtractInsideOn()
    geometry.ExtractBoundaryCellsOn()
    geometry.Update()

    return geometry.GetOutput()

def femoralHeadPMMA(femoral_head_model_bounds, spacing, origin, inval, outval, thickness, pmma_mat_id):
    """Creates the image data for the femoral head PMMA cap.
    The arguments are the femoral head model bounds, image spacing, image origin, in value of pmma, out value for pmma, pmma thickness and pmma material ID.
    Returns the Femoral Head PMMA padded image.
    """
    ##
    # Create vtkImageData for femoral head PMMA capping
    fh_pmma_id = vtk.vtkImageData()
    fh_pmma_id.SetSpacing(spacing)
    fh_pmma_id.SetExtent(
        int(femoral_head_model_bounds[0] / spacing[0]),
        int(femoral_head_model_bounds[1] / spacing[0]),
        int(femoral_head_model_bounds[2] / spacing[1]),
        int(femoral_head_model_bounds[3] / spacing[1]),
        int(femoral_head_model_bounds[4] / spacing[2]),
        int(femoral_head_model_bounds[5] / spacing[2])
    )
    fh_pmma_id.SetOrigin(origin)
    fh_pmma_id.AllocateScalars(vtk.VTK_SHORT, 1)

    ##
    # Create numpy array of PMMA cap to convert to vtkImageData
    fh_pmma_np = np.empty(fh_pmma_id.GetDimensions())
    fh_pmma_np.fill(inval)

    ##
    # Import Numpy array to vtk
    vtk_data = numpy_to_vtk(
        num_array=fh_pmma_np.ravel(),
        deep=True,
        array_type=vtk.VTK_SHORT
    )
    fh_pmma_id.GetPointData().SetScalars(vtk_data)

    ##
    # Pad Image with extra thickness
    extent2 = fh_pmma_id.GetExtent()

    fh_pmma_id_pad = vtk.vtkImageConstantPad()
    fh_pmma_id_pad.SetInputData(fh_pmma_id)
    fh_pmma_id_pad.SetOutputWholeExtent(
        extent2[0],
        extent2[1],
        extent2[2] - thickness,
        extent2[3],
        extent2[4],
        extent2[5]
    )
    fh_pmma_id_pad.SetConstant(pmma_mat_id)
    fh_pmma_id_pad.Update()
    return fh_pmma_id_pad.GetOutput()

def femoralHeadPMMA_SLS(femoral_head_model_bounds, spacing, origin, inval, outval, thickness, pmma_mat_id):
    """Creates the image data for the femoral head PMMA cap.
    The arguments are the femoral head model bounds, image spacing, image origin, in value of pmma, out value for pmma, pmma thickness and pmma material ID.
    Returns the Femoral Head PMMA padded image.
    """
    ##
    # Create vtkImageData for femoral head PMMA capping
    fh_pmma_id = vtk.vtkImageData()
    fh_pmma_id.SetSpacing(spacing)
    fh_pmma_id.SetExtent(
        int(femoral_head_model_bounds[0] / spacing[0]),
        int(femoral_head_model_bounds[1] / spacing[0]),
        int(femoral_head_model_bounds[2] / spacing[1]),
        int(femoral_head_model_bounds[3] / spacing[1]),
        int(femoral_head_model_bounds[4] / spacing[2]),
        int(femoral_head_model_bounds[5] / spacing[2])
    )
    fh_pmma_id.SetOrigin(origin)
    fh_pmma_id.AllocateScalars(vtk.VTK_SHORT, 1)

    ##
    # Create numpy array of PMMA cap to convert to vtkImageData
    fh_pmma_np = np.empty(fh_pmma_id.GetDimensions())
    fh_pmma_np.fill(inval)

    ##
    # Import Numpy array to vtk
    vtk_data = numpy_to_vtk(
        num_array=fh_pmma_np.ravel(),
        deep=True,
        array_type=vtk.VTK_SHORT
    )
    fh_pmma_id.GetPointData().SetScalars(vtk_data)

    ##
    # Pad Image with extra thickness
    extent2 = fh_pmma_id.GetExtent()

    fh_pmma_id_pad = vtk.vtkImageConstantPad()
    fh_pmma_id_pad.SetInputData(fh_pmma_id)
    fh_pmma_id_pad.SetOutputWholeExtent(
        extent2[0],
        extent2[1],
        extent2[2],
        extent2[3],
        extent2[4],
        extent2[5] + thickness
    )
    fh_pmma_id_pad.SetConstant(pmma_mat_id)
    fh_pmma_id_pad.Update()
    return fh_pmma_id_pad.GetOutput()

def finalRegistration(ref_image):
    """Performs final 3D image registration in SimpleITK.
    The first argument is the image.
    The second argument is the mask image (used for registration).
    The third argument is the reference image.
    Returns the transformed image and mask as VTKImageData.
    """

    fixed_image = sitk.ReadImage(ref_image, sitk.sitkFloat32)
    moving_image = sitk.ReadImage("temp_mask.nii", sitk.sitkFloat32)
    trans_image = sitk.ReadImage("temp_image.nii", sitk.sitkFloat32)

    message("Performing initial registration transform...")
    initial_transform = sitk.CenteredTransformInitializer(fixed_image,
                                                      moving_image,
                                                      sitk.Euler3DTransform(),
                                                      sitk.CenteredTransformInitializerFilter.MOMENTS
                                                      )
    moving_resampled = sitk.Resample(
        moving_image,
        fixed_image,
        initial_transform,
        sitk.sitkLinear,
        0.0,
        moving_image.GetPixelIDValue()
        )

    message("Setting up registration parameters...")
    registration_method = sitk.ImageRegistrationMethod()
    registration_method.SetMetricAsJointHistogramMutualInformation(
        numberOfHistogramBins=100
        )
    registration_method.SetMetricSamplingStrategy(registration_method.RANDOM)
    registration_method.SetMetricSamplingPercentage(0.01)
    registration_method.SetInterpolator(sitk.sitkLinear)
    registration_method.SetOptimizerAsGradientDescent(
        learningRate=1.0,
        numberOfIterations=100,
        convergenceMinimumValue=1e-6,
        convergenceWindowSize=10
        )
    registration_method.SetOptimizerScalesFromPhysicalShift()
    registration_method.SetShrinkFactorsPerLevel(shrinkFactors=[4, 2, 1])
    registration_method.SetSmoothingSigmasPerLevel(smoothingSigmas=[2, 1, 0])
    registration_method.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    registration_method.SetInitialTransform(initial_transform,
        inPlace=False
        )

    message("Executing the registration...")
    final_transform = registration_method.Execute(sitk.Cast(fixed_image,
        sitk.sitkFloat32),
        sitk.Cast(moving_image,
        sitk.sitkFloat32)
        )
    message("Registration complete...")

    print(('Final metric value: {0}'.format(registration_method.GetMetricValue())))
    print(('Optimizer\'s stopping condition, {0}'.format(
    registration_method.GetOptimizerStopConditionDescription())))

    message("Resampling the images...")
    moving_resampled = sitk.Resample(moving_image,
        fixed_image,
        final_transform,
        sitk.sitkLinear,
        0.0,
        moving_image.GetPixelIDValue()
        )
    moving_thres = sitk.BinaryThreshold(moving_resampled,
        lowerThreshold=0.01,
        insideValue=1,
        outsideValue=0
        )

    org_trans = sitk.Resample(trans_image,
    fixed_image,
    final_transform,
    sitk.sitkBSpline,
    0.0,
    trans_image.GetPixelIDValue()
    )

    message("Writing out temp images...")
    sitk.WriteImage(moving_thres, "temp_mask2.nii")
    sitk.WriteImage(org_trans, "temp_image2.nii")

    message("Removing temporary files...")
    os.remove("temp_image.nii")
    os.remove("temp_mask.nii")


def greaterTrochanterPMMA(greater_trochanter_model_bounds, spacing, origin, inval, outval, thickness, pmma_mat_id):
    """Creates the image data for the greater trochanter PMMA cap.
    The arguments are the femoral head model bounds, image spacing, image origin, in value of pmma, out value for pmma, pmma thickness and pmma material ID.
    Returns the Greater trochanter PMMA padded image.
    """
    ##
    # Create vtkImageData for greater trochanter PMMA capping
    gt_pmma_id = vtk.vtkImageData()
    gt_pmma_id.SetSpacing(spacing)
    gt_pmma_id.SetExtent(
        int(greater_trochanter_model_bounds[0] / spacing[0]),
        int(greater_trochanter_model_bounds[1] / spacing[0]),
        int(greater_trochanter_model_bounds[2] / spacing[1]),
        int(greater_trochanter_model_bounds[3] / spacing[1]),
        int(greater_trochanter_model_bounds[4] / spacing[2]),
        int(greater_trochanter_model_bounds[5] / spacing[2])
    )
    gt_pmma_id.SetOrigin(origin)
    gt_pmma_id.AllocateScalars(vtk.VTK_SHORT, 1)

    # Create numpy array of PMMA cap to convert to vtkImageData
    gt_pmma_np = np.empty(gt_pmma_id.GetDimensions())
    gt_pmma_np.fill(inval)

    ##
    # Import Numpy array to vtk
    vtk_data3 = numpy_to_vtk(
        num_array=gt_pmma_np.ravel(),
        deep=True,
        array_type=vtk.VTK_SHORT
    )
    gt_pmma_id.GetPointData().SetScalars(vtk_data3)

    ##
    # Pad iamge with extra thickness
    extent3 = gt_pmma_id.GetExtent()
    gt_pmma_id_pad = vtk.vtkImageConstantPad()
    gt_pmma_id_pad.SetInputData(gt_pmma_id)
    gt_pmma_id_pad.SetOutputWholeExtent(
        extent3[0],
        extent3[1],
        extent3[2],
        extent3[3] + thickness,
        extent3[4],
        extent3[5]
    )
    gt_pmma_id_pad.SetConstant(pmma_mat_id)
    gt_pmma_id_pad.Update()
    return gt_pmma_id_pad.GetOutput()

def icEffectiveEnergy(HU_array, adipose, air, blood, bone, muscle, k2hpo4, cha, triglyceride, water):
    """Used to determine the scan effective energy for internal calibration.
    The first argument is the mean HU for each tissue.
    The remaining arguments are the tissue specific interpolated tables from icInterpolation.
    Returns the scan effective energy and calibration parameters as a dictionary.
    """
    energy_r2_values = pd.DataFrame(columns = ['Energy [keV]', 'R-Squared'])
    energy_r2_values['Energy [keV]'] = adipose['Energy [keV]']

    for i in np.arange(1, len(adipose), 1):
        attenuation = [
        adipose.loc[i,'Mass Attenuation [cm2/g]'],
        air.loc[i,'Mass Attenuation [cm2/g]'],
        blood.loc[i,'Mass Attenuation [cm2/g]'],
        bone.loc[i,'Mass Attenuation [cm2/g]'],
        muscle.loc[i,'Mass Attenuation [cm2/g]']
        ]

        EE_lr = stats.linregress(HU_array, attenuation)
        r_squared = EE_lr[2]**2
        energy_r2_values.loc[i, 'R-Squared'] = r_squared

    max_row = energy_r2_values[energy_r2_values['R-Squared'] == energy_r2_values['R-Squared'].max()]
    max_r2 = energy_r2_values['R-Squared'].max()
    index = max_row.index.values.astype(int)[0]
    effective_energy = max_row.at[index, 'Energy [keV]']

    # Determine the corresponding mass attenuation values for each material
    adipose_EE = adipose.at[index, 'Mass Attenuation [cm2/g]']
    air_EE = air.at[index, 'Mass Attenuation [cm2/g]']
    blood_EE = blood.at[index, 'Mass Attenuation [cm2/g]']
    bone_EE = bone.at[index, 'Mass Attenuation [cm2/g]']
    muscle_EE = muscle.at[index, 'Mass Attenuation [cm2/g]']
    k2hpo4_EE = k2hpo4.at[index, 'Mass Attenuation [cm2/g]']
    cha_EE = cha.at[index, 'Mass Attenuation [cm2/g]']
    triglyceride_EE = triglyceride.at[index, 'Mass Attenuation [cm2/g]']
    water_EE = water.at[index, 'Mass Attenuation [cm2/g]']

    # Create dictionary for output
    dict = OrderedDict()
    dict['Effective Energy [keV]'] = effective_energy
    dict['Max R^2'] = max_r2
    dict['Adipose u/p'] = adipose_EE
    dict['Air u/p'] = air_EE
    dict['Blood u/p'] = blood_EE
    dict['Cortical Bone u/p'] = bone_EE
    dict['Skeletal Muscle u/p'] = muscle_EE
    dict['K2HPO4 u/p'] = k2hpo4_EE
    dict['CHA u/p'] = cha_EE
    dict['Triglyceride u/p'] = triglyceride_EE
    dict['Water u/p'] = water_EE

    return dict

def icInterpolation(material_table):
    """Used for internal calibration. Interpolates the material table for energy
    levels 1-200 keV.The first argument is the reference material table.
    Returns the interpolated material table for internal calibration.
    """
    energies = np.arange(1, 200.5, 0.5)
    interp_table = interp.griddata(material_table['Energy [keV]'], material_table['Mass Attenuation [cm2/g]'], energies, method = 'linear')
    interp_df = pd.DataFrame({'Energy [keV]':energies, 'Mass Attenuation [cm2/g]':interp_table})
    return interp_df

def icLinearRegression(x_values, y_values, slopeLabel, yintLabel):
    """Function for linear regression of two values.
    The first argument are the x values.
    The second argument are the y values.
    The third argument is the dictionary label for the slope.
    The fourth argument is the dictionary ladel for the y-intercept
    Returns the regression slope and y-intercept as dictionary.
    """
    linreg = stats.linregress(x_values, y_values)
    dict = OrderedDict()
    dict[slopeLabel] = linreg[0]
    dict[yintLabel] = linreg[1]
    return dict

def imageHistogramMean(imageData):
    """Creates a histogram of the input image data, ignoring zero values.
    The first argument is the input image data.
    Returns the mean value of the histogram.
    """
    accumulate = vtk.vtkImageAccumulate()
    accumulate.SetInputData(imageData)
    accumulate.IgnoreZeroOn()
    accumulate.Update()
    mean = accumulate.GetMean()
    return mean

def icMaterialDensity(material_HU, material_attenuation, water_attenuation, water_density):
    """Determines the apparent density for each material.
    The first argument is the material HU from ROI.
    The second argument is the material attenuation at the effective energy.
    The third argument is water's attenuation at the effective energy.
    The fourth argument is the assumed density of water at 1.0 g/cc.
    Returns the material density.
    """
    output_density = (material_HU/1000*water_attenuation*water_density + water_attenuation*water_density)/material_attenuation
    return output_density

def Image2Mesh(vtk_image):
    """Mesh image data to hexahedral elements."""
    mesher = vtkbone.vtkboneImageToMesh()
    mesher.SetInputData(vtk_image)
    mesher.Update()
    message("Generated %d hexahedrons" % mesher.GetOutput().GetNumberOfCells())
    message("Generated %d nodes" % mesher.GetOutput().GetNumberOfPoints())
    return mesher.GetOutput()

def imageConnectivity(vtk_image):
    """Performd image connectivity filter"""
    conn = vtkbone.vtkboneImageConnectivityFilter()
    conn.SetInputData(vtk_image)
    conn.Update()
    return conn.GetOutput()

def imageResample(vtk_image, isotropic_voxel_size):
    """Resample the input vtk image to isotropic voxel size as specified.
    The first argument is the input vtk Image Data.
    The second argument is the isotropic output voxel size.
    Returns the resampled VTK Image Data.
    """
    image_resample = vtk.vtkImageResample()
    image_resample.SetInputData(vtk_image)
    image_resample.SetInterpolationModeToCubic()
    image_resample.SetDimensionality(3)
    image_resample.SetAxisOutputSpacing(0,isotropic_voxel_size)
    image_resample.SetAxisOutputSpacing(1,isotropic_voxel_size)
    image_resample.SetAxisOutputSpacing(2,isotropic_voxel_size)
    image_resample.Update()
    return image_resample.GetOutput()

def inferiorVertebralPMMA(inferior_model_bounds, spacing, origin, inval, outval, thickness, pmma_mat_id):
    """Creates the image data for the inferior vertebral PMMA cap.
    The arguments are the inferior vertebral  model bounds, image spacing, image origin, in value of pmma, out value for pmma, pmma thickness and pmma material ID.
    Returns the Inferior Vertebral PMMA padded image.
    """
    ##
    # Create vtkImageData for inferior vertebral PMMA capping
    iv_pmma_id = vtk.vtkImageData()
    iv_pmma_id.SetSpacing(spacing)
    iv_pmma_id.SetExtent(
        int(inferior_model_bounds[0] / spacing[0]),
        int(inferior_model_bounds[1] / spacing[0]),
        int(inferior_model_bounds[2] / spacing[1]),
        int(inferior_model_bounds[3] / spacing[1]),
        int(inferior_model_bounds[4] / spacing[2]),
        int(inferior_model_bounds[5] / spacing[2])
    )
    iv_pmma_id.SetOrigin(origin)
    iv_pmma_id.AllocateScalars(vtk.VTK_SHORT, 1)

    ##
    # Create numpy array of PMMA cap to convert to vtkImageData
    iv_pmma_np = np.empty(iv_pmma_id.GetDimensions())
    iv_pmma_np.fill(inval)

    ##
    # Import Numpy array to vtk
    vtk_data = numpy_to_vtk(
        num_array=iv_pmma_np.ravel(),
        deep=True,
        array_type=vtk.VTK_SHORT
    )
    iv_pmma_id.GetPointData().SetScalars(vtk_data)

    ##
    # Pad Image with extra thickness
    extent2 = iv_pmma_id.GetExtent()

    iv_pmma_id_pad = vtk.vtkImageConstantPad()
    iv_pmma_id_pad.SetInputData(iv_pmma_id)
    iv_pmma_id_pad.SetOutputWholeExtent(
        extent2[0],
        extent2[1],
        extent2[2],
        extent2[3],
        extent2[4] - thickness,
        extent2[5]
    )
    iv_pmma_id_pad.SetConstant(pmma_mat_id)
    iv_pmma_id_pad.Update()
    return iv_pmma_id_pad.GetOutput()

def iterativeClosestPoint(source, target):
    """Performs ICP to get a transformation.
    The first argument is the source.
    The second argument is the target.
    Returns the 4x4 rotation matrix.
    """
    icp = vtk.vtkIterativeClosestPointTransform()
    icp.SetSource(source)
    icp.SetTarget(target)
    icp.StartByMatchingCentroidsOn()
    icp.GetLandmarkTransform().SetModeToRigidBody()
    icp.SetMeanDistanceModeToRMS()
    icp.SetMaximumMeanDistance(0.05)
    icp.CheckMeanDistanceOn()
    icp.SetMaximumNumberOfLandmarks(250)
    icp.SetMaximumNumberOfIterations(75)
    icp.Update()
    return icp.GetMatrix()

def marchingCubes(vtk_image):
    """Performs Marching cubes to get a surface.
    The first argument is the vtk image data.
    Returns the surface.
    """
    march = vtk.vtkImageMarchingCubes()
    march.SetInputData(vtk_image)
    march.SetValue(1,1.0)
    march.Update()
    return march.GetOutput()

def maskThreshold(imageData, threshold_value):
    """Applies the threshold value to the input image.
    The first argument is the image. The second argument is the threshold value to be applied.
    Returns the thresholded image region as image Data.
    """
    thres = vtk.vtkImageThreshold()
    thres.SetInputData(imageData)
    thres.ThresholdBetween(threshold_value, threshold_value)
    thres.ReplaceInOn()
    thres.SetInValue(1)
    thres.ReplaceOutOn()
    thres.SetOutValue(0)
    thres.SetOutputScalarTypeToUnsignedChar()
    thres.Update()
    return thres.GetOutput()

def materialTable(mesh, poissons_ratio, elastic_Emax, elastic_exponent, pmma_mat_id, pmma_E, pmma_v):
    """Defines the material table for the FE model.
    The first argument is the hexahedral mesh.
    The second argument is the bone poissons ratio.
    The 3rd argument is the power law Emax.
    The 4th is the power law exponent.
    The 5th is the pmma material ID.
    The 6th is the pmma elastic modulus.
    The 7th is the pmma poissons ratio.
    Returns the Finite Element Material Table.
    """
    # Initialize the material table
    material_table = vtkbone.vtkboneMaterialTable()

    ##
    # Create PMMA material
    pmma_material = vtkbone.vtkboneLinearIsotropicMaterial()
    pmma_material.SetName("PMMA")
    pmma_material.SetYoungsModulus(pmma_E)
    pmma_material.SetPoissonsRatio(pmma_v)
    material_table.AddMaterial(pmma_mat_id, pmma_material)

    ##
    # Determine maximum material ID: exclude PMMA
    values = vtk_to_numpy (mesh.GetCellData().GetScalars())
    max_id = int(max(values))
    # message("Maximum ID: %d" % max_id)

    # Create array of Young's Modulus values
    bone_E = np.arange(1, max_id+2, dtype=np.float32)
    # Create array of Poisson's ratio values
    bone_nu = poissons_ratio * np.ones(max_id+1, dtype=np.float32)
    bone_nu_vtk = numpy_to_vtk(bone_nu, deep=True, array_type=vtk.VTK_FLOAT)

    ##
    # Define the For loop to create the elastic modulus array
    message("Deriving Density-Elastic Modulus values for material table...")
    for i in range(1, max_id+1, 1):

        # Power law density-Elastic Modulus conversion. Requires Density in [g/cc], not [mg/cc].
        den_bin_step = 0.001
        den = i * den_bin_step
        # message("Calculated density: %8.4f" % den)
        modulus = elastic_Emax * math.pow(den, elastic_exponent)
        # message("Calculated Elastic Modulus: %8.4f" % modulus)
        bone_E[i] = modulus
        # message("ID:%d; Density(g/cc):%8.4f; Modulus(MPa):%8.4f" % (i, den, modulus))

    # Convert these numpy arrays to VTK arrays
    bone_E_vtk = numpy_to_vtk(bone_E, deep=True, array_type=vtk.VTK_FLOAT)

    # Create a material array object for bone
    bone_material_array = vtkbone.vtkboneLinearIsotropicMaterialArray()
    bone_material_array.SetName("Bone")
    bone_material_array.SetYoungsModulus(bone_E_vtk)
    bone_material_array.SetPoissonsRatio(bone_nu_vtk)

    # Add the material array to the material table
    material_table.AddMaterial(1, bone_material_array)
    return material_table

def message(msg, *additionalLines):
    """Print message with time stamp
    The first argument is printed with the a time stamp
    Subsequent arguments are printed one to a line without a time stamp
    """
    print("%8.2f %s" % (time.time() - start_time, msg))
    for line in additionalLines:
        print(" " * 9 + line)

def numpy2vtk(numpy_image, extent, spacing, origin):
    """Convert numpy image to vtk Image Data.
    The first argument is the numpy image.
    The second argument is the image extent.
    The third argument is the image spacing.
    Returns the vtk Image Data in the same shape as FLOAT data type.
    """
    dimensions = numpy_image.shape
    vtk_image = vtk.vtkImageImport()
    vtk_image.SetDataScalarTypeToFloat()
    vtk_image.SetNumberOfScalarComponents(1)
    vtk_image.SetDataExtent(0, dimensions[0] - 1, 0, dimensions[1] - 1, 0, dimensions[2] - 1)
    vtk_image.SetWholeExtent(extent)
    vtk_image.SetDataSpacing(spacing)
    vtk_image.SetDataOrigin(origin)
    vtk_image.CopyImportVoidPointer(numpy_image, numpy_image.nbytes)
    return vtk_image.GetOutput()

def phantomParameters(h2o_density, k2hpo4_density, phantom_HU):
    """Determine the slope and y-intercept for the phantom calibration.
    The first argument are the phantom specific H2O equivalent density values. The second
    argument are the phantom specific K2HPO4 equivalent density values. The third
    argument are the phantom rod mean HU values from the image and mask.
    Returns the slope and y-intercept for the calibration as a float list.
    """
    y_values = np.subtract(phantom_HU, h2o_density)
    x_values = k2hpo4_density
    regression_parameters = stats.linregress(x_values, y_values)

    # convert slope and y-intercept to CT parameters
    sigma_ct = regression_parameters[0] - 0.2174
    beta_ct = regression_parameters[1] + 999.6

    # Determine calibration parameters
    calibration_slope = 1/sigma_ct
    calibration_yint = (-1)*(beta_ct/sigma_ct)
    return {
    'Y Values':y_values,
    'X Values':x_values,
    'Regression Slope':regression_parameters[0],
    'Regression Y-Intercept':regression_parameters[1],
    'Sigma_CT':sigma_ct,
    'Beta_CT':beta_ct,
    'Calibration Slope':calibration_slope,
    'Calibration Y-Intercept':calibration_yint
    }

def phantomParameters_bmas200(cha_density, phantom_HU):
    """Determine the slope and y-intercept for the phantom calibration.
    The first argument is the phantom specific cha equivalent density values. The second
    argument are the phantom rod mean HU values from the image and mask.
    Returns the slope and y-intercept for the calibration as a float list.
    """
    x_values = phantom_HU
    y_values = cha_density
    regression_parameters = stats.linregress(x_values, y_values)

    # Determine calibration parameters
    calibration_slope = regression_parameters[0]
    calibration_yint = regression_parameters[1]
    return {
    'Calibration Slope':calibration_slope,
    'Calibration Y-Intercept':calibration_yint
    }

def point2cellData(vtk_image):
    """ Converts vtk image point data to cell data.
    The first argument is the vtk image.
    Returns the image with cell and point data.
    """
    pt2cell = vtk.vtkPointDataToCellData()
    pt2cell.SetInputData(vtk_image)
    pt2cell.PassPointDataOn()
    pt2cell.Update()
    return pt2cell.GetOutput()

def preRotateImage(image, mask, z_rotation):
    """Pre-rotation the image for ICP alignment."""
    message("Pre-rotating image...")
    spacing = image.GetSpacing()
    origin = image.GetOrigin()
    extent = image.GetExtent()
    bounds = image.GetBounds()
    center = [None]*3
    center[0] = (bounds[1] + bounds[0])/2.0
    center[1] = (bounds[3] + bounds[2])/2.0
    center[2] = (bounds[5] + bounds[4])/2.0

    transform = vtk.vtkTransform()
    transform.Translate(center[0], center[1], center[2])
    transform.RotateY(180)
    transform.RotateZ(z_rotation)
    transform.Translate(-center[0], -center[1], -center[2])

    image_reslice = vtk.vtkImageReslice()
    image_reslice.SetResliceTransform(transform)
    image_reslice.SetInterpolationModeToCubic()
    # image_reslice.AutoCropOutputOn()
    image_reslice.SetInputData(image)
    image_reslice.Update()

    # Apply transform to image and reslice
    mask_reslice = vtk.vtkImageReslice()
    mask_reslice.SetResliceTransform(transform)
    mask_reslice.SetInterpolationModeToNearestNeighbor()
    # image_reslice.AutoCropOutputOn()
    mask_reslice.SetInputData(mask)
    mask_reslice.Update()

    return image_reslice.GetOutput(), mask_reslice.GetOutput()


def readDCM(fileDir):
    """Reads a DICOM image from a directory.
    The first argument is the image directory.
    Returns the image as vtk Output Data.
    """
    image = vtk.vtkDICOMImageReader()
    image.SetDirectoryName(fileDir)
    image.Update()

    flip = vtk.vtkImageFlip()
    flip.SetInputConnection(image.GetOutputPort())
    flip.SetFilteredAxis(1)
    flip.Update()
    flip2 = vtk.vtkImageFlip()
    flip2.SetInputConnection(flip.GetOutputPort())
    flip2.SetFilteredAxis(2)
    flip2.Update()

    return flip2.GetOutput()

def readNii(filename):
    """Reads a NIFTI image.
    The first argument is the image filename.
    Returns the Image as vtk Output Data
    """
    image = vtk.vtkNIFTIImageReader()
    image.SetFileName(filename)
    image.Update()
    return image.GetOutput()

def readPolyData(vtk_poly):
    """Reads a VTK Legacy file in PolyData Format.
    The first argument is the filename.
    Returns the Poly Data reader output.
    """
    poly = vtk.vtkPolyDataReader()
    poly.SetFileName(vtk_poly)
    poly.Update()
    return poly.GetOutput()

def readTransform(transform_file):
    """Reads a *.dat file and extracts 4x4 rotation matrix.
    The first argument is the filename.
    Returns the 4x4 transformation matrix.
    """
    transform_data = open(transform_file, 'r+')
    data = transform_data.readlines()
    transform_data.close()


    matrix = [
            data[2].strip().split(),
            data[3].strip().split(),
            data[4].strip().split(),
            data[5].strip().split()
            ]

    m = vtk.vtkMatrix4x4()
    m.SetElement(0,0, float(matrix[0][0]))
    m.SetElement(0,1, float(matrix[0][1]))
    m.SetElement(0,2, float(matrix[0][2]))
    m.SetElement(0,3, float(matrix[0][3]))
    m.SetElement(1,0, float(matrix[1][0]))
    m.SetElement(1,1, float(matrix[1][1]))
    m.SetElement(1,2, float(matrix[1][2]))
    m.SetElement(1,3, float(matrix[1][3]))
    m.SetElement(2,0, float(matrix[2][0]))
    m.SetElement(2,1, float(matrix[2][1]))
    m.SetElement(2,2, float(matrix[2][2]))
    m.SetElement(2,3, float(matrix[2][3]))
    m.SetElement(3,0, float(matrix[3][0]))
    m.SetElement(3,1, float(matrix[3][1]))
    m.SetElement(3,2, float(matrix[3][2]))
    m.SetElement(3,3, float(matrix[3][3]))

    return m

def sitk2numpy(sitk_image):
    numpy_image = sitk.GetArrayFromImage(sitk_image)
    return numpy_image

def superiorVertebralPMMA(superior_model_bounds, spacing, origin, inval, outval, thickness, pmma_mat_id):
    """Creates the image data for the superior vertebral PMMA cap.
    The arguments are the superior vertebral  model bounds, image spacing, image origin, in value of pmma, out value for pmma, pmma thickness and pmma material ID.
    Returns the Superior Vertebral PMMA padded image.
    """
    ##
    # Create vtkImageData for superior vertebral PMMA capping
    sv_pmma_id = vtk.vtkImageData()
    sv_pmma_id.SetSpacing(spacing)
    sv_pmma_id.SetOrigin(origin)
    sv_pmma_id.SetExtent(
        int(superior_model_bounds[0] / spacing[0]),
        int(superior_model_bounds[1] / spacing[0]),
        int(superior_model_bounds[2] / spacing[1]),
        int(superior_model_bounds[3] / spacing[1]),
        int(superior_model_bounds[4] / spacing[2]),
        int(superior_model_bounds[5] / spacing[2])
    )
    sv_pmma_id.AllocateScalars(vtk.VTK_SHORT, 1)

    ##
    # Create numpy array of PMMA cap to convert to vtkImageData
    sv_pmma_np = np.empty(sv_pmma_id.GetDimensions())
    sv_pmma_np.fill(inval)

    ##
    # Import Numpy array to vtk
    vtk_data = numpy_to_vtk(
        num_array=sv_pmma_np.ravel(),
        deep=True,
        array_type=vtk.VTK_SHORT
    )
    sv_pmma_id.GetPointData().SetScalars(vtk_data)

    ##
    # Pad Image with extra thickness
    extent2 = sv_pmma_id.GetExtent()

    sv_pmma_id_pad = vtk.vtkImageConstantPad()
    sv_pmma_id_pad.SetInputData(sv_pmma_id)
    sv_pmma_id_pad.SetOutputWholeExtent(
        extent2[0],
        extent2[1],
        extent2[2],
        extent2[3],
        extent2[4],
        extent2[5] + thickness
    )
    sv_pmma_id_pad.SetConstant(pmma_mat_id)
    sv_pmma_id_pad.Update()

    return sv_pmma_id_pad.GetOutput()

def vertebralBodyExtract(image, mask_image):
    """Extracts the body of the vertebra from the whole vertebra for FE.
    The first argument is the vertebra mask.
    Returns the mask of just the vertebral body.
    """
    message("Generating vertebra surface...")
    surface = marchingCubes(mask_image)
    bounds = surface.GetBounds()
    message("Model Bounds: %s" % str(bounds))
    image_bounds = [
                    int(bounds[0]),
                    int(bounds[1]),
                    int((bounds[2]+bounds[3])/2),
                    int(bounds[3]),
                    int(bounds[4]),
                    int(bounds[5])
                    ]

    message("Extracting Body VOI...")
    extract = vtk.vtkExtractVOI()
    extract.SetInputData(mask_image)
    extract.SetVOI(image_bounds)
    extract.SetSampleRate(1,1,1)
    extract.IncludeBoundaryOn()
    extract.Update()

    message("Eroding the body mask...")
    erode = vtk.vtkImageContinuousErode3D()
    erode.SetInputData(extract.GetOutput())
    erode.SetKernelSize(21,21,21)
    erode.Update()

    message("Extracting Largest connected component...")
    conn = imageConnectivity(erode.GetOutput())

    message("Dilating the body mask...")
    dilate = vtk.vtkImageContinuousDilate3D()
    dilate.SetInputData(conn)
    dilate.SetKernelSize(50,25,50)
    dilate.Update()

    message("Boolean of vertebra and dialtion masks...")
    logic = vtk.vtkImageLogic()
    logic.SetInput1Data(dilate.GetOutput())
    logic.SetInput2Data(mask_image)
    logic.SetOperationToAnd()
    logic.SetOutputTrueValue(1)
    logic.Update()

    message("Subtracting Body from Vertebral Arch and Pedicles...")
    math = vtk.vtkImageMathematics()
    math.SetOperationToSubtract()
    math.SetInput1Data(mask_image)
    math.SetInput2Data(logic.GetOutput())
    math.Update()

    message("Obtaining Arch and Pedicles mask...")
    pedicles = imageConnectivity(math.GetOutput())

    message("Determining final vertebral body...")
    body = vtk.vtkImageMathematics()
    body.SetOperationToSubtract()
    body.SetInput1Data(mask_image)
    body.SetInput2Data(pedicles)
    body.Update()

    final_body_mask = body.GetOutput()

    bone_image = applyMask(image, final_body_mask)

    return image, final_body_mask

def vtk2numpy(vtk_image):
    """Convert vtk image data to a numpy array in same shape.
    The first argument is the vtk image data.
    Returns the numpy array.
    """
    numpy_image = vtk_to_numpy(vtk_image.GetPointData().GetScalars())
    numpy_image.shape = vtk_image.GetDimensions()
    return numpy_image

def writeN88Model(model, fileName, pathname):
    """Writes out a N88Model.
    The first argument is the model.
    The second argument is the filename.
    The third argument is the pathname.
    Returns the N88model in the directory.
    """
    os.chdir(pathname)
    writer = vtkbone.vtkboneN88ModelWriter()
    writer.SetInputData(model)
    writer.SetFileName(fileName)
    writer.Update()

def writeNii(imageData, fileName, output_directory):
    """Writes out an input image as a NIFTI file.
    The first argument is the image Data. The second argument is the filename. The third argument is the output directory where the file is to be written to.
    """
    os.chdir(output_directory)
    writer = vtk.vtkNIFTIImageWriter()
    writer.SetInputData(imageData)
    writer.SetFileName(fileName)
    writer.Write()

def writeTXTfile(input_dict, fileName, output_directory):
    """Write a text file containing the parameters in the input array.
    The first argument is the input array of two columns. The first column is the
    variable name, the second column is the variable data. The second argument is the
    filename. The third argument is the output directory.
    Output is the text file with the information.
    """
    os.chdir(output_directory)
    txt_file = open(fileName, "w")
    for key, value in list(input_dict.items()):
        txt_file.write(str(key) + '\t' + str(value) + '\n')
    txt_file.close()
